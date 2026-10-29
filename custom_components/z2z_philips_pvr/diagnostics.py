"""Diagnostics with credentials redacted."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import PhilipsPvrConfigEntry

TO_REDACT = {CONF_USERNAME, CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PhilipsPvrConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data.data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "version": data.version if data else None,
        "powerstate": data.powerstate if data else None,
        "storage": data.storage if data else None,
        "current_channel": data.current_channel if data else None,
        "channel_count": len(data.channels) if data else 0,
        "recordings": [rec.raw for rec in data.recordings] if data else [],
    }
