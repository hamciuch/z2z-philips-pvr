"""Base entity."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, MANUFACTURER
from .coordinator import PhilipsPvrCoordinator
from .models import PvrData, Recording


class PhilipsPvrEntity(CoordinatorEntity[PhilipsPvrCoordinator]):
    """Entity bound to one TV."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PhilipsPvrCoordinator, key: str) -> None:
        """Initialise."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer=MANUFACTURER,
            name=f"{entry.title} PVR",
            model="JointSPACE PVR",
            configuration_url=None,
        )
        self._host = entry.data[CONF_HOST]

    @property
    def pvr(self) -> PvrData:
        """Coordinator data."""
        return self.coordinator.data


def recording_summary(data: PvrData, rec: Recording) -> dict[str, Any]:
    """Compact, JSON-friendly description of a recording for attributes/responses."""
    return {
        "id": rec.recording_id,
        "name": rec.name,
        "channel": data.channel_name(rec.ccid) or rec.ccid,
        "start": dt_util.as_local(rec.start).isoformat(),
        "end": dt_util.as_local(rec.end).isoformat(),
        "duration_min": round(rec.duration.total_seconds() / 60),
        "status": rec.type.removeprefix("RECORDING_").lower(),
        "error": None if rec.error == "REC_ERROR_NONE" else rec.error,
    }
