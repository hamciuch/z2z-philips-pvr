"""Model parsing tests."""

from datetime import UTC, datetime, timedelta

from custom_components.z2z_philips_pvr.models import Recording, manual_recording_payload


def test_from_api_strings() -> None:
    rec = Recording.from_api(
        {
            "RecordingId": 121,
            "RecordingType": "RECORDING_NEW",
            "RecError": "REC_ERROR_NONE",
            "ccid": 3181,
            "StartTime": 1793277180,
            "Duration": 119,
            "EventId": 0,
            "RecName": "DW",
        }
    )
    assert rec.recording_id == 121
    assert rec.is_finished and not rec.is_failed
    assert rec.duration == timedelta(seconds=119)
    assert rec.start.tzinfo is UTC


def test_from_api_numbers() -> None:
    """Database-style numeric enums are mapped to names."""
    rec = Recording.from_api(
        {
            "RecordingId": 1,
            "RecordingType": 8,
            "RecError": 11,
            "ChannelId": 5,
            "StartTime": 0,
        }
    )
    assert rec.type == "RECORDING_FAILED"
    assert rec.error == "REC_ERROR_NO_CAM"
    assert rec.ccid == 5
    assert rec.is_failed


def test_scheduled_and_ongoing() -> None:
    assert Recording.from_api({"RecordingType": "RECORDING_MANUAL"}).is_scheduled
    assert Recording.from_api({"RecordingType": "RECORDING_SCHEDULED"}).is_scheduled
    assert Recording.from_api({"RecordingType": "RECORDING_ONGOING"}).is_ongoing


def test_manual_payload_matches_verified_body() -> None:
    start = datetime(2026, 10, 29, 12, 40, tzinfo=UTC)
    body = manual_recording_payload(3181, start, timedelta(minutes=5), "DW")
    assert body["RecordingType"] == "RECORDING_MANUAL"
    assert body["EventId"] == ""
    assert body["ccid"] == 3181
    assert body["StartTime"] == int(start.timestamp())
    assert body["Duration"] == 300
    assert body["IsIpEpgRec"] is False
