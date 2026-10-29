"""Service tests."""

from datetime import timedelta

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.z2z_philips_pvr.const import DOMAIN

from .conftest import FakeTV


async def test_record_by_preset_number(
    hass: HomeAssistant, setup_integration: MockConfigEntry, fake_tv: FakeTV
) -> None:
    start = dt_util.now() + timedelta(hours=2)
    resp = await hass.services.async_call(
        DOMAIN,
        "record",
        {
            "channel": "808",
            "start": start.replace(tzinfo=None).isoformat(),
            "duration": {"minutes": 90},
            "name": "Film",
        },
        blocking=True,
        return_response=True,
    )
    assert resp["recording_id"] == 119
    assert resp["confirmed"] is True
    assert resp["channel"] == "DW (English)"
    body = fake_tv.added[0]
    assert body["ccid"] == 3181
    assert body["RecordingType"] == "RECORDING_MANUAL"
    assert body["Duration"] == 5400
    assert body["RecName"] == "Film"
    # naive datetime is interpreted in HA local time (Europe/Warsaw)
    assert abs(body["StartTime"] - start.timestamp()) < 1
    # CAM warning: TV is on and showing TVP INFO, recording DW
    assert any("NO_CAM" in w for w in resp["warnings"])
    assert hass.states.get("sensor.65pus8857_12_pvr_scheduled_recordings").state == "1"


async def test_record_by_name_with_end(
    hass: HomeAssistant, setup_integration: MockConfigEntry, fake_tv: FakeTV
) -> None:
    start = dt_util.now() + timedelta(hours=1)
    end = start + timedelta(minutes=30)
    resp = await hass.services.async_call(
        DOMAIN,
        "record",
        {"channel": "tvp info hd", "start": start.isoformat(), "end": end.isoformat()},
        blocking=True,
        return_response=True,
    )
    assert fake_tv.added[0]["ccid"] == 2993
    assert fake_tv.added[0]["Duration"] == 1800
    assert resp["name"] == "TVP INFO HD"
    assert resp["warnings"] == []  # same channel as watched


async def test_record_already_running_programme(
    hass: HomeAssistant, setup_integration: MockConfigEntry, fake_tv: FakeTV
) -> None:
    start = dt_util.now() - timedelta(minutes=10)
    await hass.services.async_call(
        DOMAIN,
        "record",
        {"channel": "27", "start": start.isoformat(), "duration": {"minutes": 40}},
        blocking=True,
        return_response=True,
    )
    body = fake_tv.added[0]
    assert body["StartTime"] > dt_util.utcnow().timestamp()
    assert 28 * 60 < body["Duration"] < 30 * 60


async def test_record_unknown_channel(
    hass: HomeAssistant, setup_integration: MockConfigEntry, fake_tv: FakeTV
) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "record",
            {
                "channel": "Nope",
                "start": dt_util.now().isoformat(),
                "duration": {"minutes": 5},
            },
            blocking=True,
            return_response=True,
        )
    assert fake_tv.added == []


async def test_record_requires_end_or_duration(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "record",
            {"channel": "27", "start": dt_util.now().isoformat()},
            blocking=True,
            return_response=True,
        )


async def test_record_conflict(
    hass: HomeAssistant, setup_integration: MockConfigEntry, fake_tv: FakeTV
) -> None:
    fake_tv.conflicts = [
        {
            "RecordingId": 1,
            "RecName": "Film AXN",
            "ResolveAction": "resolve_action_delete",
        }
    ]
    data = {
        "channel": "27",
        "start": (dt_util.now() + timedelta(hours=1)).isoformat(),
        "duration": {"minutes": 5},
    }
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "record", data, blocking=True, return_response=True
        )
    assert fake_tv.added == []
    resp = await hass.services.async_call(
        DOMAIN, "record", {**data, "force": True}, blocking=True, return_response=True
    )
    assert resp["recording_id"] == 119
    assert any("conflicts" in w for w in resp["warnings"])


async def test_record_too_long(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "record",
            {
                "channel": "27",
                "start": (dt_util.now() + timedelta(hours=1)).isoformat(),
                "duration": {"hours": 13},
            },
            blocking=True,
            return_response=True,
        )


async def test_record_now_current_channel(
    hass: HomeAssistant, setup_integration: MockConfigEntry, fake_tv: FakeTV
) -> None:
    resp = await hass.services.async_call(
        DOMAIN,
        "record_now",
        {"duration": {"minutes": 45}},
        blocking=True,
        return_response=True,
    )
    body = fake_tv.added[0]
    assert body["ccid"] == 2993
    lead = body["StartTime"] - dt_util.utcnow().timestamp()
    assert 60 <= lead <= 140
    assert body["StartTime"] % 60 == 0
    assert resp["warnings"] == []


async def test_record_now_tv_off_needs_channel(
    hass: HomeAssistant, setup_integration: MockConfigEntry, fake_tv: FakeTV
) -> None:
    fake_tv.powerstate = "Standby"
    await setup_integration.runtime_data.async_refresh()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "record_now", {}, blocking=True, return_response=True
        )
    resp = await hass.services.async_call(
        DOMAIN, "record_now", {"channel": "310"}, blocking=True, return_response=True
    )
    assert fake_tv.added[0]["ccid"] == 310
    assert resp["warnings"] == []  # standby: CAM is free


async def test_delete_with_503_quirk(
    hass: HomeAssistant, setup_integration: MockConfigEntry, fake_tv: FakeTV
) -> None:
    resp = await hass.services.async_call(
        DOMAIN,
        "delete_recording",
        {"recording_id": 2},
        blocking=True,
        return_response=True,
    )
    assert resp == {"deleted": [2]}
    assert fake_tv.deleted == [2]
    assert hass.states.get("sensor.65pus8857_12_pvr_recordings").state == "1"


async def test_delete_not_applied(
    hass: HomeAssistant, setup_integration: MockConfigEntry, fake_tv: FakeTV
) -> None:
    fake_tv.delete_works = False
    with pytest.raises(HomeAssistantError, match="did not delete"):
        await hass.services.async_call(
            DOMAIN,
            "delete_recording",
            {"recording_id": [1]},
            blocking=True,
            return_response=True,
        )


async def test_delete_unknown(
    hass: HomeAssistant, setup_integration: MockConfigEntry, fake_tv: FakeTV
) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "delete_recording",
            {"recording_id": 999},
            blocking=True,
            return_response=True,
        )
    assert fake_tv.deleted == []
