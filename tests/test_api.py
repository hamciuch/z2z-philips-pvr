"""API client tests against a mocked HTTP transport (incl. the TV quirks)."""

from __future__ import annotations

import json

import httpx
import pytest

from custom_components.z2z_philips_pvr.api import (
    PhilipsPvrApi,
    PhilipsPvrAuthError,
    PhilipsPvrConnectionError,
    PhilipsPvrError,
    PhilipsPvrRecordingError,
)

CHALLENGE = 'Digest realm="XTV", nonce="abc123", qop="auth", algorithm=MD5'


def make_api(handler) -> PhilipsPvrApi:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return PhilipsPvrApi(client, "192.168.23.100", "user", "pass")


async def test_digest_auth_and_url() -> None:
    """First request is challenged, second carries a digest Authorization header."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "authorization" not in request.headers:
            return httpx.Response(401, headers={"WWW-Authenticate": CHALLENGE})
        return httpx.Response(200, json={"name": "TV", "jsonfeatures": {}})

    api = make_api(handler)
    assert (await api.get_system())["name"] == "TV"
    assert str(seen[0].url) == "https://192.168.23.100:1926/6/system"
    assert seen[-1].headers["authorization"].startswith("Digest ")
    assert 'username="user"' in seen[-1].headers["authorization"]


async def test_rejected_credentials() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, headers={"WWW-Authenticate": CHALLENGE})

    with pytest.raises(PhilipsPvrAuthError):
        await make_api(handler).get_recordings()


async def test_empty_list_is_none() -> None:
    """The TV sometimes answers 200 with an empty body ("not modified")."""
    api = make_api(lambda r: httpx.Response(200, content=b""))
    assert await api.get_recordings() is None


async def test_list_parsed() -> None:
    body = {"version": "610.291", "recordings": [{"RecordingId": 1}]}
    api = make_api(lambda r: httpx.Response(200, json=body))
    assert await api.get_recordings() == body


async def test_list_bad_payload() -> None:
    api = make_api(lambda r: httpx.Response(200, json={"foo": 1}))
    with pytest.raises(PhilipsPvrError):
        await api.get_recordings()


async def test_add_ok_and_body() -> None:
    sent: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        assert request.url.path == "/6/recordings/add"
        return httpx.Response(200, json={"Error": "rec_error_none", "RecordingId": 119})

    assert await make_api(handler).add_recording({"ccid": 3181}) == 119
    assert sent == {"ccid": 3181}


async def test_add_refused() -> None:
    api = make_api(lambda r: httpx.Response(200, json={"Error": "rec_error_conflict"}))
    with pytest.raises(PhilipsPvrRecordingError) as err:
        await api.add_recording({})
    assert err.value.code == "rec_error_conflict"


@pytest.mark.parametrize("status", [200, 503])
async def test_delete_accepts_503(status: int) -> None:
    """groupaction delete answers 503 although it works — must not raise."""
    sent: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return httpx.Response(status, text="<html>Service Unavailable</html>")

    await make_api(handler).delete_recordings([119, 120])
    assert sent == {
        "actions": [
            {"action": "delete", "data": {"RecordingId": 119}},
            {"action": "delete", "data": {"RecordingId": 120}},
        ]
    }


async def test_delete_other_error_raises() -> None:
    api = make_api(lambda r: httpx.Response(500))
    with pytest.raises(PhilipsPvrError):
        await api.delete_recordings([1])


async def test_conflict_check_empty_object() -> None:
    api = make_api(lambda r: httpx.Response(200, json={}))
    assert await api.conflict_check({}) == []


async def test_conflict_check_list() -> None:
    api = make_api(
        lambda r: httpx.Response(200, json=[{"RecordingId": 5, "RecName": "X"}])
    )
    assert await api.conflict_check({}) == [{"RecordingId": 5, "RecName": "X"}]


async def test_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("boom", request=request)

    with pytest.raises(PhilipsPvrConnectionError):
        await make_api(handler).get_powerstate()


async def test_current_channel_and_channels() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("activities/tv"):
            return httpx.Response(
                200,
                json={"channel": {"ccid": 2993, "preset": "27", "name": "TVP INFO HD"}},
            )
        return httpx.Response(
            200, json={"Channel": [{"ccid": 1, "preset": "1", "name": "A"}]}
        )

    api = make_api(handler)
    assert (await api.get_current_channel())["ccid"] == 2993
    assert await api.get_channels() == [{"ccid": 1, "preset": "1", "name": "A"}]
