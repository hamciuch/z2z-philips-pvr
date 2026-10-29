"""Services: record, record_now, delete_recording."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .api import PhilipsPvrError, PhilipsPvrRecordingError
from .const import (
    ATTR_CHANNEL,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_DURATION,
    ATTR_END,
    ATTR_FORCE,
    ATTR_NAME,
    ATTR_RECORDING_ID,
    ATTR_START,
    DOMAIN,
    POWER_ON,
    SERVICE_DELETE,
    SERVICE_RECORD,
    SERVICE_RECORD_NOW,
)
from .coordinator import PhilipsPvrCoordinator
from .models import manual_recording_payload

_LOGGER = logging.getLogger(__name__)

MIN_DURATION = timedelta(minutes=1)
MAX_DURATION = timedelta(hours=12)
# The TV sets its start alarm ~1 minute before a MANUAL recording, so "now" means
# the first full minute at least this far ahead.
RECORD_NOW_LEAD = timedelta(seconds=75)

_ENTRY = vol.Optional(ATTR_CONFIG_ENTRY_ID)
_CHANNEL = vol.All(vol.Coerce(str), cv.string)

RECORD_SCHEMA = vol.All(
    vol.Schema(
        {
            _ENTRY: cv.string,
            vol.Required(ATTR_CHANNEL): _CHANNEL,
            vol.Required(ATTR_START): cv.datetime,
            vol.Exclusive(ATTR_END, "stop"): cv.datetime,
            vol.Exclusive(ATTR_DURATION, "stop"): cv.positive_time_period,
            vol.Optional(ATTR_NAME): cv.string,
            vol.Optional(ATTR_FORCE, default=False): cv.boolean,
        }
    ),
    cv.has_at_least_one_key(ATTR_END, ATTR_DURATION),
)

RECORD_NOW_SCHEMA = vol.Schema(
    {
        _ENTRY: cv.string,
        vol.Optional(ATTR_CHANNEL): _CHANNEL,
        vol.Optional(
            ATTR_DURATION, default=timedelta(hours=1)
        ): cv.positive_time_period,
        vol.Optional(ATTR_NAME): cv.string,
        vol.Optional(ATTR_FORCE, default=False): cv.boolean,
    }
)

DELETE_SCHEMA = vol.Schema(
    {
        _ENTRY: cv.string,
        vol.Required(ATTR_RECORDING_ID): vol.All(
            cv.ensure_list, [vol.Coerce(int)], vol.Length(min=1)
        ),
    }
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt_util.get_default_time_zone())
    return dt_util.as_utc(value)


def _get_coordinator(hass: HomeAssistant, call: ServiceCall) -> PhilipsPvrCoordinator:
    entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if entry_id:
        entries = [entry for entry in entries if entry.entry_id == entry_id]
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="no_entry"
        )
    if len(entries) > 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="multiple_entries"
        )
    return entries[0].runtime_data


def _resolve_channel(coordinator: PhilipsPvrCoordinator, value: str) -> int:
    ccid = coordinator.find_channel(value)
    if ccid is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_channel",
            translation_placeholders={"channel": str(value)},
        )
    return ccid


def _cam_warning(coordinator: PhilipsPvrCoordinator, ccid: int) -> str | None:
    """Warn when the TV is on and watching another channel (CAM busy → NO_CAM)."""
    data = coordinator.data
    if data is None or data.powerstate != POWER_ON or not data.current_channel:
        return None
    try:
        watched = int(data.current_channel.get("ccid"))
    except (TypeError, ValueError):
        return None
    if watched == ccid:
        return None
    return (
        f"TV is on and showing '{data.current_channel.get('name', watched)}'. "
        "If the recorded channel needs the CI card and the TV still shows another "
        "channel at that time, the recording may fail with REC_ERROR_NO_CAM."
    )


async def _schedule(
    coordinator: PhilipsPvrCoordinator,
    ccid: int,
    start: datetime,
    duration: timedelta,
    name: str | None,
    force: bool,
) -> dict[str, Any]:
    if not MIN_DURATION <= duration <= MAX_DURATION:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="invalid_duration"
        )
    if start + duration <= dt_util.utcnow():
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="in_the_past"
        )

    channel_name = (
        coordinator.data.channel_name(ccid) if coordinator.data else None
    ) or str(ccid)
    title = name or channel_name
    payload = manual_recording_payload(ccid, start, duration, title)

    try:
        conflicts = await coordinator.api.conflict_check(payload)
    except PhilipsPvrError as err:
        raise HomeAssistantError(f"Conflict check failed: {err}") from err
    if conflicts and not force:
        names = ", ".join(
            str(c.get("RecName") or c.get("RecordingId") or "?") for c in conflicts
        )
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="conflict",
            translation_placeholders={"conflicts": names},
        )

    try:
        recording_id = await coordinator.api.add_recording(payload)
    except PhilipsPvrRecordingError as err:
        raise HomeAssistantError(f"TV refused the recording: {err.code}") from err
    except PhilipsPvrError as err:
        raise HomeAssistantError(f"Could not schedule recording: {err}") from err

    confirmed = await coordinator.async_refresh_until(
        lambda data: any(r.recording_id == recording_id for r in data.recordings)
    )
    if not confirmed:
        _LOGGER.warning(
            "Recording %s was accepted but is not yet visible in the TV list",
            recording_id,
        )

    warnings = [w for w in (_cam_warning(coordinator, ccid),) if w]
    if conflicts:
        warnings.append(f"Scheduled despite conflicts: {conflicts}")
    for warning in warnings:
        _LOGGER.warning(warning)

    return {
        "recording_id": recording_id,
        "channel": channel_name,
        "ccid": ccid,
        "start": dt_util.as_local(start).isoformat(),
        "end": dt_util.as_local(start + duration).isoformat(),
        "name": title,
        "confirmed": confirmed,
        "warnings": warnings,
    }


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration services."""

    async def record(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass, call)
        ccid = _resolve_channel(coordinator, call.data[ATTR_CHANNEL])
        start = _as_utc(call.data[ATTR_START])
        if ATTR_END in call.data:
            duration = _as_utc(call.data[ATTR_END]) - start
        else:
            duration = call.data[ATTR_DURATION]
        now = dt_util.utcnow()
        if start < now:
            # Already running programme: record the rest of it.
            duration -= now - start
            start = now + RECORD_NOW_LEAD
        return await _schedule(
            coordinator,
            ccid,
            start,
            duration,
            call.data.get(ATTR_NAME),
            call.data[ATTR_FORCE],
        )

    async def record_now(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass, call)
        if ATTR_CHANNEL in call.data:
            ccid = _resolve_channel(coordinator, call.data[ATTR_CHANNEL])
        else:
            current = coordinator.data.current_channel if coordinator.data else None
            if not current or coordinator.data.powerstate != POWER_ON:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="no_current_channel"
                )
            ccid = int(current["ccid"])
        start = (dt_util.utcnow() + RECORD_NOW_LEAD).replace(
            second=0, microsecond=0
        ) + timedelta(minutes=1)
        return await _schedule(
            coordinator,
            ccid,
            start,
            call.data[ATTR_DURATION],
            call.data.get(ATTR_NAME),
            call.data[ATTR_FORCE],
        )

    async def delete_recording(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass, call)
        ids: list[int] = call.data[ATTR_RECORDING_ID]
        known = (
            {r.recording_id for r in coordinator.data.recordings}
            if coordinator.data
            else set()
        )
        missing = [i for i in ids if i not in known]
        if missing:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_recording",
                translation_placeholders={"ids": ", ".join(map(str, missing))},
            )
        try:
            await coordinator.api.delete_recordings(ids)
        except PhilipsPvrError as err:
            raise HomeAssistantError(f"Delete failed: {err}") from err
        # The TV answers 503 even on success — the list is the source of truth.
        wanted = set(ids)
        gone = await coordinator.async_refresh_until(
            lambda data: not wanted & {r.recording_id for r in data.recordings}
        )
        if not gone:
            raise HomeAssistantError(
                f"TV did not delete recording(s) {', '.join(map(str, ids))}"
            )
        return {"deleted": ids}

    hass.services.async_register(
        DOMAIN,
        SERVICE_RECORD,
        record,
        schema=RECORD_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RECORD_NOW,
        record_now,
        schema=RECORD_NOW_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE,
        delete_recording,
        schema=DELETE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
