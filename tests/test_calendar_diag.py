"""Calendar and diagnostics tests."""

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.z2z_philips_pvr.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import FakeTV, rec


async def test_calendar_events(
    hass: HomeAssistant, setup_integration: MockConfigEntry, fake_tv: FakeTV
) -> None:
    fake_tv.recordings.append(
        rec(130, "RECORDING_MANUAL", 2993, 120, 1800, RecName="Wiadomości")
    )
    await setup_integration.runtime_data.async_refresh()
    now = dt_util.now()
    resp = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "entity_id": "calendar.65pus8857_12_pvr_recordings",
            "start_date_time": (now - timedelta(days=1)).isoformat(),
            "end_date_time": (now + timedelta(days=1)).isoformat(),
        },
        blocking=True,
        return_response=True,
    )
    events = resp["calendar.65pus8857_12_pvr_recordings"]["events"]
    summaries = [e["summary"] for e in events]
    assert summaries == ["Film AXN", "Rec 2", "Wiadomości"]
    assert events[2]["location"] == "TVP INFO HD"
    assert "REC_ERROR_NO_CAM" in events[1]["description"]


async def test_diagnostics_redacted(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    diag = await async_get_config_entry_diagnostics(hass, setup_integration)
    assert diag["entry"]["username"] == "**REDACTED**"
    assert diag["entry"]["password"] == "**REDACTED**"
    assert len(diag["recordings"]) == 2
