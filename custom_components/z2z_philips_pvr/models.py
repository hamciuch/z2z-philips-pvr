"""Data models for Z2Z Philips PVR."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .const import (
    ERROR_BY_NUMBER,
    ERROR_NONE,
    FAILED_TYPES,
    ONGOING_TYPES,
    SCHEDULED_TYPES,
    TYPE_BY_NUMBER,
    TYPE_MANUAL,
)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _enum(value: Any, table: dict[int, str]) -> str:
    """Accept both enum names (API) and numbers (TV database)."""
    if isinstance(value, str) and not value.isdigit():
        return value
    number = _int(value, -1)
    return table.get(number, str(value))


@dataclass(frozen=True, slots=True)
class Recording:
    """One row of ``recordings/list`` (a recording or a scheduled recording)."""

    recording_id: int
    type: str
    error: str
    ccid: int
    start: datetime
    duration: timedelta
    margin_start: timedelta
    margin_end: timedelta
    name: str
    event_id: int
    size: int | None
    actual_start: datetime | None
    raw: dict[str, Any] = field(repr=False, compare=False, hash=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Recording:
        """Build from one ``recordings/list`` item."""
        actual = _int(data.get("ActualStartTime") or data.get("Actual_Start_Time"), 0)
        size = data.get("Size")
        return cls(
            recording_id=_int(data.get("RecordingId")),
            type=_enum(data.get("RecordingType"), TYPE_BY_NUMBER),
            error=_enum(data.get("RecError", 0), ERROR_BY_NUMBER),
            ccid=_int(data.get("ccid", data.get("ChannelId"))),
            start=datetime.fromtimestamp(_int(data.get("StartTime")), UTC),
            duration=timedelta(seconds=_int(data.get("Duration"))),
            margin_start=timedelta(seconds=_int(data.get("MarginStart"))),
            margin_end=timedelta(seconds=_int(data.get("MarginEnd"))),
            name=str(data.get("RecName") or data.get("EventName") or "").strip(),
            event_id=_int(data.get("EventId")),
            size=_int(size) if size not in (None, "") else None,
            actual_start=(datetime.fromtimestamp(actual, UTC) if actual > 0 else None),
            raw=data,
        )

    @property
    def end(self) -> datetime:
        """Planned end of the recording."""
        return self.start + self.duration

    @property
    def planned_stop(self) -> datetime:
        """Planned end including the end margin."""
        return self.end + self.margin_end

    @property
    def is_scheduled(self) -> bool:
        """Recording waiting to start."""
        return self.type in SCHEDULED_TYPES

    @property
    def is_ongoing(self) -> bool:
        """Recording in progress."""
        return self.type in ONGOING_TYPES

    @property
    def is_failed(self) -> bool:
        """Recording that failed (or finished with an error)."""
        return self.type in FAILED_TYPES or (
            self.error not in (ERROR_NONE, "") and not self.is_scheduled
        )

    @property
    def is_finished(self) -> bool:
        """A recording that exists on disk (or failed) — not scheduled, not ongoing."""
        return not self.is_scheduled and not self.is_ongoing


@dataclass(slots=True)
class PvrData:
    """Everything the coordinator knows about the TV."""

    recordings: list[Recording]
    version: str | None
    storage: dict[str, Any] | None
    powerstate: str | None
    current_channel: dict[str, Any] | None
    channels: dict[int, str]
    presets: dict[str, int] = field(default_factory=dict)

    def channel_name(self, ccid: int) -> str | None:
        """Name of a channel by ccid."""
        return self.channels.get(ccid)

    @property
    def scheduled(self) -> list[Recording]:
        """Scheduled recordings, soonest first."""
        return sorted(
            (r for r in self.recordings if r.is_scheduled), key=lambda r: r.start
        )

    @property
    def ongoing(self) -> list[Recording]:
        """Recordings in progress."""
        return [r for r in self.recordings if r.is_ongoing]

    @property
    def finished(self) -> list[Recording]:
        """Recorded (or failed) items, newest first."""
        return sorted(
            (r for r in self.recordings if r.is_finished),
            key=lambda r: r.start,
            reverse=True,
        )


def manual_recording_payload(
    ccid: int, start: datetime, duration: timedelta, name: str
) -> dict[str, Any]:
    """Body for ``recordings/add``/``conflictcheck`` of a time-based (MANUAL) recording.

    Verified on the TV: MANUAL with an empty ``EventId`` is accepted and records by time.
    """
    return {
        "RecordingType": TYPE_MANUAL,
        "IsIpEpgRec": False,
        "ccid": int(ccid),
        "StartTime": int(start.timestamp()),
        "Duration": int(duration.total_seconds()),
        "MarginStart": 0,
        "MarginEnd": 0,
        "EventId": "",
        "RecName": name,
        "EventName": name,
        "EventInfo": "",
        "EventExtendedInfo": "",
        "EventGenre": "0",
    }
