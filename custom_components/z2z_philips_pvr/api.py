"""Minimal async client for the Philips JointSPACE recordings API (v6, port 1926).

Behaviour observed on a 65PUS8857/12 (Android TV 11), see docs/recording-research.md:
- every call needs HTTP digest auth (the credentials paired by the Philips TV integration),
- ``GET recordings/list`` sometimes answers ``200`` with an empty body ("list not modified"),
- ``POST recordings/groupaction`` (delete) answers ``503`` although the delete succeeds,
- ``POST recordings/add`` answers ``{"Error": "rec_error_none", "RecordingId": N}``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from .const import ADD_ERROR_NONE, DEFAULT_API_VERSION, DEFAULT_PORT, REQUEST_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class PhilipsPvrError(Exception):
    """Generic API error."""


class PhilipsPvrConnectionError(PhilipsPvrError):
    """The TV could not be reached."""


class PhilipsPvrAuthError(PhilipsPvrError):
    """Credentials were rejected."""


class PhilipsPvrRecordingError(PhilipsPvrError):
    """The TV refused to create a recording."""

    def __init__(self, code: str) -> None:
        """Store the TV error code."""
        super().__init__(code)
        self.code = code


class PhilipsPvrApi:
    """Talk to the JointSPACE API of one TV."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        host: str,
        username: str,
        password: str,
        *,
        port: int = DEFAULT_PORT,
        api_version: int = DEFAULT_API_VERSION,
    ) -> None:
        """Initialise the client. ``client`` must not verify TLS (self-signed cert)."""
        self._client = client
        self._base = f"https://{host}:{port}/{api_version}/"
        # One DigestAuth instance so the nonce is reused between requests.
        self._auth = httpx.DigestAuth(username, password)

    async def _request(
        self, method: str, path: str, payload: Any = None
    ) -> httpx.Response:
        try:
            response = await self._client.request(
                method,
                self._base + path,
                json=payload,
                auth=self._auth,
                timeout=REQUEST_TIMEOUT,
            )
        except httpx.TimeoutException as err:
            raise PhilipsPvrConnectionError(f"Timeout calling {path}") from err
        except httpx.HTTPError as err:
            raise PhilipsPvrConnectionError(f"Error calling {path}: {err}") from err
        if response.status_code == 401:
            raise PhilipsPvrAuthError("Authentication rejected by the TV")
        return response

    @staticmethod
    def _json(response: httpx.Response, path: str) -> Any:
        """Decode a JSON body; ``None`` for an empty body."""
        if response.status_code != 200:
            raise PhilipsPvrError(f"{path}: HTTP {response.status_code}")
        if not response.content or not response.content.strip():
            return None
        try:
            return response.json()
        except (ValueError, json.JSONDecodeError) as err:
            raise PhilipsPvrError(f"{path}: invalid JSON") from err

    async def _get(self, path: str) -> Any:
        return self._json(await self._request("GET", path), path)

    async def _post(self, path: str, payload: Any) -> Any:
        return self._json(await self._request("POST", path, payload), path)

    # --- read -----------------------------------------------------------------

    async def get_system(self) -> dict[str, Any]:
        """Return ``/system`` (used to validate the connection)."""
        data = await self._get("system")
        if not isinstance(data, dict):
            raise PhilipsPvrError("system: empty response")
        return data

    async def get_recordings(self) -> dict[str, Any] | None:
        """Return ``{"version": ..., "recordings": [...]}`` or ``None`` if not modified/empty."""
        data = await self._get("recordings/list")
        if data is None:
            return None
        if not isinstance(data, dict) or not isinstance(data.get("recordings"), list):
            raise PhilipsPvrError("recordings/list: unexpected payload")
        return data

    async def get_storage(self) -> dict[str, Any] | None:
        """Return the recordings disk state."""
        return await self._get("system/storage")

    async def get_powerstate(self) -> str | None:
        """Return ``On``/``Standby``... or ``None``."""
        data = await self._get("powerstate")
        if isinstance(data, dict):
            return data.get("powerstate")
        return None

    async def get_current_channel(self) -> dict[str, Any] | None:
        """Return ``{"ccid": .., "preset": .., "name": ..}`` of the watched channel."""
        data = await self._get("activities/tv")
        if isinstance(data, dict) and isinstance(data.get("channel"), dict):
            return data["channel"]
        return None

    async def get_channels(self) -> list[dict[str, Any]]:
        """Return all channels of the ``all`` channel list."""
        data = await self._get("channeldb/tv/channelLists/all")
        if isinstance(data, dict) and isinstance(data.get("Channel"), list):
            return data["Channel"]
        return []

    # --- write ----------------------------------------------------------------

    async def conflict_check(self, recording: dict[str, Any]) -> list[dict[str, Any]]:
        """Return conflicts for a recording (empty list if none). Writes nothing."""
        data = await self._post("recordings/conflictcheck", recording)
        if not data:
            return []
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("conflicts", "Conflicts", "recordings"):
                if isinstance(data.get(key), list):
                    return data[key]
            return [data]
        return []

    async def add_recording(self, recording: dict[str, Any]) -> int:
        """Schedule a recording and return its ``RecordingId``."""
        data = await self._post("recordings/add", recording)
        if not isinstance(data, dict):
            raise PhilipsPvrError("recordings/add: empty response")
        error = str(data.get("Error", "")).lower()
        if error != ADD_ERROR_NONE:
            raise PhilipsPvrRecordingError(data.get("Error") or "unknown")
        try:
            return int(data["RecordingId"])
        except (KeyError, TypeError, ValueError) as err:
            raise PhilipsPvrError("recordings/add: no RecordingId") from err

    async def delete_recordings(self, recording_ids: list[int]) -> None:
        """Delete recordings.

        The TV answers ``503`` even when the delete worked, so any 2xx/503 is accepted
        and the caller must verify the result with :meth:`get_recordings`.
        """
        payload = {
            "actions": [
                {"action": "delete", "data": {"RecordingId": int(rec_id)}}
                for rec_id in recording_ids
            ]
        }
        response = await self._request("POST", "recordings/groupaction", payload)
        if response.status_code not in (200, 204, 503):
            raise PhilipsPvrError(
                f"recordings/groupaction: HTTP {response.status_code}"
            )
        if response.status_code == 503:
            _LOGGER.debug(
                "groupaction answered 503 (known TV quirk), verifying via list"
            )
