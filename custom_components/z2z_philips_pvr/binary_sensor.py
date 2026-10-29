"""Binary sensors: recording in progress, disk problem, stuck recording, failure."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import OVERRUN_GRACE, STORAGE_MOUNTED
from .coordinator import PhilipsPvrConfigEntry, overrun_limit
from .entity import PhilipsPvrEntity, recording_summary
from .models import PvrData

PARALLEL_UPDATES = 0

# A failure older than this no longer raises the "last recording failed" problem.
FAILURE_WINDOW_DAYS = 2


def _overrunning(data: PvrData) -> list:
    now = dt_util.utcnow()
    return [r for r in data.ongoing if now > overrun_limit(r, OVERRUN_GRACE)]


def _recent_failures(data: PvrData) -> list:
    since = dt_util.utcnow() - timedelta(days=FAILURE_WINDOW_DAYS)
    return [r for r in data.finished if r.is_failed and r.start >= since]


@dataclass(frozen=True, kw_only=True)
class PvrBinaryDescription(BinarySensorEntityDescription):
    """Binary sensor description."""

    is_on_fn: Callable[[PvrData], bool | None]
    attrs_fn: Callable[[PvrData], dict[str, Any]] | None = None


BINARY_SENSORS: tuple[PvrBinaryDescription, ...] = (
    PvrBinaryDescription(
        key="recording",
        device_class=BinarySensorDeviceClass.RUNNING,
        is_on_fn=lambda d: bool(d.ongoing),
        attrs_fn=lambda d: {"recordings": [recording_summary(d, r) for r in d.ongoing]},
    ),
    PvrBinaryDescription(
        key="disk_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda d: (
            None if d.storage is None else d.storage.get("status") != STORAGE_MOUNTED
        ),
        attrs_fn=lambda d: {"status": (d.storage or {}).get("status")},
    ),
    PvrBinaryDescription(
        key="overrun",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda d: bool(_overrunning(d)),
        attrs_fn=lambda d: {
            "recordings": [recording_summary(d, r) for r in _overrunning(d)]
        },
    ),
    PvrBinaryDescription(
        key="failed",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda d: bool(_recent_failures(d)),
        attrs_fn=lambda d: {
            "recordings": [recording_summary(d, r) for r in _recent_failures(d)]
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PhilipsPvrConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    async_add_entities(PvrBinarySensor(entry.runtime_data, d) for d in BINARY_SENSORS)


class PvrBinarySensor(PhilipsPvrEntity, BinarySensorEntity):
    """A PVR binary sensor."""

    entity_description: PvrBinaryDescription

    def __init__(self, coordinator, description: PvrBinaryDescription) -> None:
        """Initialise."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """State."""
        return self.entity_description.is_on_fn(self.pvr)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Attributes."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.pvr)
