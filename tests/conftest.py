"""Fixtures: a fake TV that mimics the quirks observed on a 65PUS8857/12."""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.z2z_philips_pvr.api import PhilipsPvrAuthError
from custom_components.z2z_philips_pvr.const import DOMAIN

HOST = "192.168.23.100"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations."""


@pytest.fixture(autouse=True)
def no_sleep() -> Generator[None]:
    """Do not wait in retry loops."""
    with (
        patch(
            "custom_components.z2z_philips_pvr.coordinator.EMPTY_LIST_RETRY_DELAY", 0
        ),
        patch("custom_components.z2z_philips_pvr.coordinator.VERIFY_DELAY", 0),
    ):
        yield


def rec(
    rec_id: int,
    rtype: str,
    ccid: int,
    start_offset_min: int,
    duration_s: int,
    **extra: Any,
) -> dict[str, Any]:
    """Build a recordings/list item."""
    start = int((dt_util.utcnow() + timedelta(minutes=start_offset_min)).timestamp())
    return {
        "RecordingId": rec_id,
        "RecordingType": rtype,
        "RecError": extra.pop("RecError", "REC_ERROR_NONE"),
        "ccid": ccid,
        "StartTime": start,
        "Duration": duration_s,
        "MarginStart": 0,
        "MarginEnd": 0,
        "EventId": 0,
        "RecName": extra.pop("RecName", f"Rec {rec_id}"),
        **extra,
    }


class FakeTV:
    """In-memory stand-in for PhilipsPvrApi."""

    def __init__(self) -> None:
        self.recordings: list[dict[str, Any]] = [
            rec(1, "RECORDING_NEW", 310, -600, 3600, RecName="Film AXN"),
            rec(2, "RECORDING_FAILED", 3181, -300, 120, RecError="REC_ERROR_NO_CAM"),
        ]
        self.version = 1
        self.channels = [
            {"ccid": 2993, "preset": "27", "name": "TVP INFO HD"},
            {"ccid": 3181, "preset": "808", "name": "DW (English)"},
            {"ccid": 310, "preset": "310", "name": "AXN Black"},
        ]
        self.powerstate = "On"
        self.current = {"ccid": 2993, "preset": "27", "name": "TVP INFO HD"}
        self.storage = {
            "status": "Mounted",
            "totalcapacity": 238384,
            "recordingstotal": 238384,
            "recordingsusage": 63202,
        }
        self.empty_list_responses = 0
        self.conflicts: list[dict[str, Any]] = []
        self.added: list[dict[str, Any]] = []
        self.deleted: list[int] = []
        self.delete_works = True
        self.auth_ok = True
        self.next_id = 119

    def _auth(self) -> None:
        if not self.auth_ok:
            raise PhilipsPvrAuthError("401")

    async def get_system(self) -> dict[str, Any]:
        self._auth()
        return {
            "name": "65PUS8857/12",
            "jsonfeatures": {"recordings": ["List", "Schedule", "Manage"]},
        }

    async def get_recordings(self) -> dict[str, Any] | None:
        self._auth()
        if self.empty_list_responses:
            self.empty_list_responses -= 1
            return None
        return {"version": f"610.{self.version}", "recordings": list(self.recordings)}

    async def get_storage(self) -> dict[str, Any]:
        return self.storage

    async def get_powerstate(self) -> str:
        return self.powerstate

    async def get_current_channel(self) -> dict[str, Any] | None:
        return self.current

    async def get_channels(self) -> list[dict[str, Any]]:
        return self.channels

    async def conflict_check(self, recording: dict[str, Any]) -> list[dict[str, Any]]:
        return self.conflicts

    async def add_recording(self, recording: dict[str, Any]) -> int:
        self.added.append(recording)
        rec_id = self.next_id
        self.next_id += 1
        self.recordings.append(
            {**recording, "RecordingId": rec_id, "RecError": "REC_ERROR_NONE"}
        )
        self.version += 1
        return rec_id

    async def delete_recordings(self, ids: list[int]) -> None:
        # Real TV answers 503 here; the API wrapper swallows it. Deletion may or may not happen.
        self.deleted.extend(ids)
        if self.delete_works:
            self.recordings = [
                r for r in self.recordings if r["RecordingId"] not in ids
            ]
            self.version += 1


@pytest.fixture
def fake_tv() -> Generator[FakeTV]:
    """Patch the API class everywhere with a FakeTV instance."""
    tv = FakeTV()
    factory = lambda *args, **kwargs: tv  # noqa: E731
    with (
        patch("custom_components.z2z_philips_pvr.PhilipsPvrApi", side_effect=factory),
        patch(
            "custom_components.z2z_philips_pvr.config_flow.PhilipsPvrApi",
            side_effect=factory,
        ),
    ):
        yield tv


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A config entry for the TV."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="65PUS8857/12",
        unique_id=HOST,
        data={CONF_HOST: HOST, CONF_USERNAME: "user", CONF_PASSWORD: "pass"},
    )


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_tv: FakeTV
) -> MockConfigEntry:
    """Set up the integration with the fake TV."""
    await hass.config.async_set_time_zone("Europe/Warsaw")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
