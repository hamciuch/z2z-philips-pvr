#!/usr/bin/env python3
"""Live smoke test of the integration's API client against a real TV.

Uses the same api.py/models.py as the integration (without Home Assistant).

    pip install httpx
    python3 scripts/smoke_test.py 192.168.23.100            # read-only
    python3 scripts/smoke_test.py 192.168.23.100 --write    # + add & delete a test recording

Credentials are read from ~/.philips-tv.env (PHILIPS_USER=..., PHILIPS_PASS=...)
or the PHILIPS_USER / PHILIPS_PASS environment variables. Nothing is printed or stored.

--write schedules a 1-minute MANUAL recording tomorrow at 03:00 local time on the first
channel, checks it appears in the list, deletes it (the TV answers 503 — expected) and
checks it is gone. Nothing is actually recorded.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

import httpx

PKG_DIR = (
    Path(__file__).resolve().parent.parent / "custom_components" / "z2z_philips_pvr"
)

# Load const/api/models as a package without running __init__.py (which needs HA).
_pkg = types.ModuleType("pvr")
_pkg.__path__ = [str(PKG_DIR)]
sys.modules["pvr"] = _pkg
api_mod = importlib.import_module("pvr.api")
models = importlib.import_module("pvr.models")


def load_credentials() -> tuple[str, str]:
    env = {}
    path = Path.home() / ".philips-tv.env"
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip().removeprefix("export ").strip()
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip('"').strip("'")
    user = os.environ.get("PHILIPS_USER") or env.get("PHILIPS_USER")
    password = os.environ.get("PHILIPS_PASS") or env.get("PHILIPS_PASS")
    if not user or not password:
        sys.exit(
            "No credentials: create ~/.philips-tv.env with PHILIPS_USER and PHILIPS_PASS"
        )
    return user, password


def ok(msg: str) -> None:
    print(f"  OK   {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL {msg}")


async def find(api, rec_id: int, present: bool, attempts: int = 6) -> bool:
    for _ in range(attempts):
        data = await api.get_recordings()
        if data is not None:
            ids = {int(r.get("RecordingId", -1)) for r in data["recordings"]}
            if (rec_id in ids) == present:
                return True
        await asyncio.sleep(2)
    return False


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("host")
    parser.add_argument(
        "--write", action="store_true", help="add and delete a test recording"
    )
    args = parser.parse_args()
    user, password = load_credentials()
    failures = 0

    async with httpx.AsyncClient(verify=False) as client:
        api = api_mod.PhilipsPvrApi(client, args.host, user, password)
        print(f"Philips PVR smoke test → {args.host}")

        system = await api.get_system()
        features = (system.get("jsonfeatures") or {}).get("recordings")
        ok(f"system: {system.get('name')} recordings={features}")
        if not features or "List" not in features:
            fail("recordings API not declared")
            failures += 1

        ok(f"powerstate: {await api.get_powerstate()}")
        current = await api.get_current_channel()
        ok(f"current channel: {current}")
        channels = await api.get_channels()
        ok(f"channels: {len(channels)}")
        storage = await api.get_storage()
        ok(f"storage: {storage}")

        listing = None
        for _ in range(3):
            listing = await api.get_recordings()
            if listing is not None:
                break
            print("  ...  empty 200 (list not modified), retrying")
            await asyncio.sleep(2)
        if listing is None:
            fail("recordings/list stayed empty")
            return 1
        recs = [models.Recording.from_api(r) for r in listing["recordings"]]
        names = {int(c["ccid"]): c.get("name") for c in channels if "ccid" in c}
        ok(f"recordings: {len(recs)} (version {listing.get('version')})")
        for rec in sorted(recs, key=lambda r: r.start, reverse=True)[:5]:
            print(
                f"       #{rec.recording_id:<4} {rec.start.astimezone():%Y-%m-%d %H:%M} "
                f"{rec.duration.seconds // 60:>4} min  {names.get(rec.ccid, rec.ccid)!s:<20} "
                f"{rec.type} {rec.error}  {rec.name}"
            )
        unknown_types = {r.type for r in recs if not r.type.startswith("RECORDING_")}
        if unknown_types:
            fail(f"unparsed RecordingType values: {unknown_types}")
            failures += 1

        if not channels:
            fail("no channels — cannot test scheduling")
            return 1
        ccid = int((current or channels[0])["ccid"])
        start = (datetime.now().astimezone() + timedelta(days=1)).replace(
            hour=3, minute=0, second=0, microsecond=0
        )
        payload = models.manual_recording_payload(
            ccid, start, timedelta(minutes=1), "Z2Z smoke test"
        )
        conflicts = await api.conflict_check(payload)
        ok(
            f"conflictcheck ({names.get(ccid)} {start:%Y-%m-%d %H:%M}): {conflicts or 'none'}"
        )

        if not args.write:
            print("Read-only run finished. Use --write to test add/delete.")
            return 1 if failures else 0

        rec_id = await api.add_recording(payload)
        ok(f"add → RecordingId {rec_id}")
        if await find(api, rec_id, present=True):
            ok("recording visible in list")
        else:
            fail("recording not visible in list")
            failures += 1
        await api.delete_recordings([rec_id])
        ok("groupaction delete sent (503 is expected)")
        if await find(api, rec_id, present=False):
            ok("recording gone from list")
        else:
            fail(f"recording {rec_id} still present — delete it on the TV!")
            failures += 1

    print("PASSED" if not failures else f"{failures} FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except api_mod.PhilipsPvrAuthError:
        sys.exit("FAIL credentials rejected (401) — check ~/.philips-tv.env")
    except api_mod.PhilipsPvrError as err:
        sys.exit(f"FAIL {err}")
