"""Coordinator polling the TV recordings list."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import PhilipsPvrApi, PhilipsPvrAuthError, PhilipsPvrError
from .const import CHANNELS_REFRESH, DOMAIN, POWER_ON, SCAN_INTERVAL
from .models import PvrData, Recording

_LOGGER = logging.getLogger(__name__)

# The TV sometimes answers recordings/list with an empty 200; retry once after this delay.
EMPTY_LIST_RETRY_DELAY = 2.0
# Delay between re-reads when verifying a write (add/delete).
VERIFY_DELAY = 2.0

type PhilipsPvrConfigEntry = ConfigEntry[PhilipsPvrCoordinator]


class PhilipsPvrCoordinator(DataUpdateCoordinator[PvrData]):
    """Poll recordings, storage, power state and current channel."""

    config_entry: PhilipsPvrConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: PhilipsPvrConfigEntry, api: PhilipsPvrApi
    ) -> None:
        """Initialise."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.api = api
        self._channels: dict[int, str] = {}
        self._presets: dict[str, int] = {}
        self._channels_fetched: datetime | None = None

    async def _fetch_recordings(self) -> dict | None:
        data = await self.api.get_recordings()
        if data is None:
            await asyncio.sleep(EMPTY_LIST_RETRY_DELAY)
            data = await self.api.get_recordings()
        return data

    async def _refresh_channels(self) -> None:
        now = dt_util.utcnow()
        if (
            self._channels
            and self._channels_fetched
            and now - self._channels_fetched < CHANNELS_REFRESH
        ):
            return
        try:
            channels = await self.api.get_channels()
        except PhilipsPvrError as err:
            _LOGGER.debug("Could not fetch channel list: %s", err)
            return
        mapping: dict[int, str] = {}
        presets: dict[str, int] = {}
        for channel in channels:
            try:
                ccid = int(channel["ccid"])
            except (KeyError, TypeError, ValueError):
                continue
            mapping[ccid] = str(channel.get("name", "")).strip()
            preset = str(channel.get("preset", "")).strip()
            if preset:
                presets.setdefault(preset, ccid)
        if mapping:
            self._channels = mapping
            self._presets = presets
            self._channels_fetched = now

    async def _async_update_data(self) -> PvrData:
        try:
            listing = await self._fetch_recordings()
            await self._refresh_channels()
            storage = await self.api.get_storage()
            powerstate = await self.api.get_powerstate()
            current = (
                await self.api.get_current_channel() if powerstate == POWER_ON else None
            )
        except PhilipsPvrAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PhilipsPvrError as err:
            raise UpdateFailed(str(err)) from err

        if listing is None:
            # "List not modified": keep what we had. Without previous data, fail the update.
            if self.data is None:
                raise UpdateFailed("TV returned an empty recordings list")
            recordings = self.data.recordings
            version = self.data.version
        else:
            recordings = []
            for item in listing["recordings"]:
                if not isinstance(item, dict):
                    continue
                try:
                    recordings.append(Recording.from_api(item))
                except (TypeError, ValueError, OverflowError) as err:
                    _LOGGER.debug("Skipping malformed recording %s: %s", item, err)
            version = listing.get("version")

        return PvrData(
            recordings=recordings,
            version=version,
            storage=storage,
            powerstate=powerstate,
            current_channel=current,
            channels=dict(self._channels),
            presets=dict(self._presets),
        )

    async def async_refresh_until(self, predicate, attempts: int = 4) -> bool:
        """Refresh until ``predicate(data)`` is true. Used to verify writes."""
        for attempt in range(attempts):
            if attempt:
                await asyncio.sleep(VERIFY_DELAY)
            await self.async_refresh()
            if self.last_update_success and self.data and predicate(self.data):
                return True
        return False

    def find_channel(self, value: str | int) -> int | None:
        """Resolve a channel given as preset number (as on the remote), name or ccid."""
        if self.data is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if text in self.data.presets:
            return self.data.presets[text]
        lowered = text.casefold()
        for ccid, name in self.data.channels.items():
            if name.casefold() == lowered:
                return ccid
        if text.isdigit() and int(text) in self.data.channels:
            return int(text)
        return None


def overrun_limit(recording: Recording, grace: timedelta) -> datetime:
    """Moment after which an ONGOING recording is considered stuck."""
    return recording.planned_stop + grace
