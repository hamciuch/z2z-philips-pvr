"""Constants for Z2Z Philips PVR."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "z2z_philips_pvr"
MANUFACTURER: Final = "Philips"

DEFAULT_API_VERSION: Final = 6
DEFAULT_PORT: Final = 1926

SCAN_INTERVAL: Final = timedelta(seconds=60)
CHANNELS_REFRESH: Final = timedelta(hours=6)
REQUEST_TIMEOUT: Final = 15

# A recording still ONGOING this long after its planned end is reported as a problem.
# The TV is known to overrun in standby (test: 12 min instead of 2), so keep it generous.
OVERRUN_GRACE: Final = timedelta(minutes=15)

PHILIPS_JS_DOMAIN: Final = "philips_js"

CONF_SOURCE_ENTRY: Final = "source_entry"

# Services
SERVICE_RECORD: Final = "record"
SERVICE_RECORD_NOW: Final = "record_now"
SERVICE_DELETE: Final = "delete_recording"

ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_CHANNEL: Final = "channel"
ATTR_START: Final = "start"
ATTR_END: Final = "end"
ATTR_DURATION: Final = "duration"
ATTR_NAME: Final = "name"
ATTR_RECORDING_ID: Final = "recording_id"
ATTR_FORCE: Final = "force"

# RecordingType values as returned in JSON (enum names).
TYPE_SCHEDULED: Final = "RECORDING_SCHEDULED"
TYPE_MANUAL: Final = "RECORDING_MANUAL"
TYPE_OTR: Final = "RECORDING_OTR"
TYPE_ONGOING: Final = "RECORDING_ONGOING"
TYPE_NEW: Final = "RECORDING_NEW"
TYPE_PARTIALLY_VIEWED: Final = "RECORDING_PARTIALLY_VIEWED"
TYPE_VIEWED: Final = "RECORDING_VIEWED"
TYPE_EXPIRED: Final = "RECORDING_EXPIRED"
TYPE_FAILED: Final = "RECORDING_FAILED"
TYPE_AUTO_SCHEDULED: Final = "RECORDING_AUTO_PVR_SCHEDULED"
TYPE_AUTO_ONGOING: Final = "RECORDING_AUTO_PVR_ONGOING"
TYPE_AUTO_FAILED: Final = "RECORDING_AUTO_PVR_FAILED"

# Numeric values used by the TV database, in case the API ever returns numbers.
TYPE_BY_NUMBER: Final = {
    0: TYPE_SCHEDULED,
    1: TYPE_MANUAL,
    2: TYPE_OTR,
    3: TYPE_ONGOING,
    4: TYPE_NEW,
    5: TYPE_PARTIALLY_VIEWED,
    6: TYPE_VIEWED,
    7: TYPE_EXPIRED,
    8: TYPE_FAILED,
    9: "RECORDING_USER_STOPPED",
    10: "RECORDING_USER_DELETED",
    11: TYPE_AUTO_SCHEDULED,
    12: TYPE_AUTO_ONGOING,
    13: TYPE_AUTO_FAILED,
    14: "RECORDING_AUTO_PVR_NEW",
    15: "RECORDING_AUTO_PVR_EXPIRED",
}

SCHEDULED_TYPES: Final = frozenset({TYPE_SCHEDULED, TYPE_MANUAL, TYPE_AUTO_SCHEDULED})
ONGOING_TYPES: Final = frozenset({TYPE_ONGOING, TYPE_OTR, TYPE_AUTO_ONGOING})
FAILED_TYPES: Final = frozenset({TYPE_FAILED, TYPE_AUTO_FAILED})

ERROR_NONE: Final = "REC_ERROR_NONE"
ADD_ERROR_NONE: Final = "rec_error_none"

ERROR_BY_NUMBER: Final = {
    0: "REC_ERROR_NONE",
    1: "REC_ERROR_DISKFULL",
    2: "REC_ERROR_CONFLICT",
    3: "REC_ERROR_NOPOWER",
    4: "REC_ERROR_POWERINTERRUPTION",
    5: "REC_ERROR_NODISK",
    6: "REC_ERROR_IOERROR",
    7: "REC_ERROR_EVENT_NOT_TRANSMITTED",
    8: "REC_ERROR_NO_TRUSTED_CLOCK",
    9: "REC_ERROR_TV_BUSY",
    10: "REC_ERROR_NO_SIGNAL",
    11: "REC_ERROR_NO_CAM",
    12: "REC_ERROR_EPG_NOTACTIVE",
    13: "REC_ERROR_SYSTEM",
}

STORAGE_MOUNTED: Final = "Mounted"
POWER_ON: Final = "On"
