"""Calendar of scheduled and finished recordings (read-only)."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import PhilipsPvrConfigEntry
from .entity import PhilipsPvrEntity
from .models import PvrData, Recording

PARALLEL_UPDATES = 0


def _event(data: PvrData, rec: Recording) -> CalendarEvent:
    channel = data.channel_name(rec.ccid) or str(rec.ccid)
    status = rec.type.removeprefix("RECORDING_").lower()
    description = f"{channel} · {status}"
    if rec.error not in ("", "REC_ERROR_NONE"):
        description += f" · {rec.error}"
    end = rec.end if rec.end > rec.start else rec.start + timedelta(minutes=1)
    if rec.is_ongoing:
        # The TV can overrun the planned end (seen in standby) — keep the event open.
        end = max(end, dt_util.utcnow() + timedelta(minutes=1))
    return CalendarEvent(
        start=dt_util.as_local(rec.start),
        end=dt_util.as_local(end),
        summary=rec.name or channel,
        description=description,
        location=channel,
        uid=str(rec.recording_id),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PhilipsPvrConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the calendar."""
    async_add_entities([PvrCalendar(entry.runtime_data)])


class PvrCalendar(PhilipsPvrEntity, CalendarEntity):
    """Recordings as calendar events."""

    def __init__(self, coordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "calendar")

    @property
    def event(self) -> CalendarEvent | None:
        """Current or next scheduled/ongoing recording."""
        data = self.pvr
        now = dt_util.utcnow()
        candidates = sorted(
            (
                r
                for r in data.recordings
                if r.is_ongoing or (r.is_scheduled and r.end > now)
            ),
            key=lambda r: r.start,
        )
        return _event(data, candidates[0]) if candidates else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Events overlapping the requested window."""
        data = self.pvr
        start_utc = dt_util.as_utc(start_date)
        end_utc = dt_util.as_utc(end_date)
        return [
            _event(data, rec)
            for rec in sorted(data.recordings, key=lambda r: r.start)
            if rec.start < end_utc and (rec.end > start_utc or rec.is_ongoing)
        ]
