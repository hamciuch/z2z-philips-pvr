"""Sensors: recordings, scheduled, next recording, disk."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PhilipsPvrConfigEntry
from .entity import PhilipsPvrEntity, recording_summary
from .models import PvrData

MAX_LISTED = 20

PARALLEL_UPDATES = 0


def _storage(data: PvrData, key: str) -> float | None:
    try:
        return float((data.storage or {})[key])
    except (KeyError, TypeError, ValueError):
        return None


def _free_gb(data: PvrData) -> float | None:
    total = _storage(data, "recordingstotal") or _storage(data, "totalcapacity")
    used = _storage(data, "recordingsusage")
    if total is None or used is None:
        return None
    return round((total - used) / 1024, 1)


def _used_pct(data: PvrData) -> float | None:
    total = _storage(data, "recordingstotal") or _storage(data, "totalcapacity")
    used = _storage(data, "recordingsusage")
    if not total or used is None:
        return None
    return round(used / total * 100, 1)


def _next(data: PvrData) -> datetime | None:
    return data.scheduled[0].start if data.scheduled else None


def _next_attrs(data: PvrData) -> dict[str, Any]:
    return recording_summary(data, data.scheduled[0]) if data.scheduled else {}


@dataclass(frozen=True, kw_only=True)
class PvrSensorDescription(SensorEntityDescription):
    """Sensor description with value/attribute callbacks."""

    value_fn: Callable[[PvrData], Any]
    attrs_fn: Callable[[PvrData], dict[str, Any]] | None = None


SENSORS: tuple[PvrSensorDescription, ...] = (
    PvrSensorDescription(
        key="recordings",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.finished),
        attrs_fn=lambda d: {
            "recordings": [recording_summary(d, r) for r in d.finished[:MAX_LISTED]]
        },
    ),
    PvrSensorDescription(
        key="scheduled",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.scheduled),
        attrs_fn=lambda d: {
            "scheduled": [recording_summary(d, r) for r in d.scheduled[:MAX_LISTED]]
        },
    ),
    PvrSensorDescription(
        key="next_recording",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_next,
        attrs_fn=_next_attrs,
    ),
    PvrSensorDescription(
        key="disk_free",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_free_gb,
    ),
    PvrSensorDescription(
        key="disk_used",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_used_pct,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PhilipsPvrConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    async_add_entities(PvrSensor(entry.runtime_data, d) for d in SENSORS)


class PvrSensor(PhilipsPvrEntity, SensorEntity):
    """A PVR sensor."""

    entity_description: PvrSensorDescription

    def __init__(self, coordinator, description: PvrSensorDescription) -> None:
        """Initialise."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Value."""
        return self.entity_description.value_fn(self.pvr)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Attributes."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.pvr)
