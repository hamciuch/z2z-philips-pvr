"""Setup, coordinator and entity tests."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from .conftest import FakeTV, rec


async def test_setup_and_entities(
    hass: HomeAssistant, setup_integration: MockConfigEntry, fake_tv: FakeTV
) -> None:
    assert setup_integration.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.65pus8857_12_pvr_recordings").state == "2"
    assert hass.states.get("sensor.65pus8857_12_pvr_scheduled_recordings").state == "0"
    assert hass.states.get("sensor.65pus8857_12_pvr_next_recording").state == "unknown"
    free = float(hass.states.get("sensor.65pus8857_12_pvr_disk_free").state)
    assert round(free, 1) == round((238384 - 63202) / 1024, 1)
    assert (
        hass.states.get("binary_sensor.65pus8857_12_pvr_recording_disk").state == "off"
    )
    assert (
        hass.states.get("binary_sensor.65pus8857_12_pvr_recording_failed").state == "on"
    )
    assert hass.states.get("binary_sensor.65pus8857_12_pvr_recording").state == "off"
    attrs = hass.states.get("sensor.65pus8857_12_pvr_recordings").attributes[
        "recordings"
    ]
    assert attrs[0]["channel"] in ("DW (English)", "AXN Black")
    assert {a["channel"] for a in attrs} == {"DW (English)", "AXN Black"}


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_tv: FakeTV
) -> None:
    fake_tv.auth_ok = False
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    assert any(
        flow["context"]["source"] == "reauth"
        for flow in hass.config_entries.flow.async_progress()
    )


async def test_first_refresh_empty_twice_fails(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_tv: FakeTV
) -> None:
    """Empty 200 on first load (twice) → retry setup later, not crash."""
    fake_tv.empty_list_responses = 2
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_empty_list_keeps_previous(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    fake_tv: FakeTV,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An empty 200 ("not modified") must not wipe the known recordings."""
    fake_tv.empty_list_responses = 2
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.65pus8857_12_pvr_recordings").state == "2"


async def test_ongoing_and_overrun(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    fake_tv: FakeTV,
    freezer: FrozenDateTimeFactory,
) -> None:
    # Started 30 min ago, planned 2 min → still ONGOING (like the standby test) → overrun.
    fake_tv.recordings.append(rec(122, "RECORDING_ONGOING", 3181, -30, 120))
    fake_tv.recordings.append(
        rec(123, "RECORDING_MANUAL", 3181, 60, 3600, RecName="Wieczorny film")
    )
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.65pus8857_12_pvr_recording").state == "on"
    assert (
        hass.states.get("binary_sensor.65pus8857_12_pvr_recording_overrun").state
        == "on"
    )
    assert hass.states.get("sensor.65pus8857_12_pvr_scheduled_recordings").state == "1"
    nxt = hass.states.get("sensor.65pus8857_12_pvr_next_recording")
    assert nxt.attributes["name"] == "Wieczorny film"
    assert nxt.attributes["id"] == 123
    cal = hass.states.get("calendar.65pus8857_12_pvr_recordings")
    assert cal.state == "on"  # ongoing recording is the current event


async def test_disk_unmounted(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    fake_tv: FakeTV,
    freezer: FrozenDateTimeFactory,
) -> None:
    fake_tv.storage = {"status": "NotMounted"}
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert (
        hass.states.get("binary_sensor.65pus8857_12_pvr_recording_disk").state == "on"
    )
    assert hass.states.get("sensor.65pus8857_12_pvr_disk_free").state == "unknown"


async def test_unload(hass: HomeAssistant, setup_integration: MockConfigEntry) -> None:
    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    assert setup_integration.state is ConfigEntryState.NOT_LOADED
