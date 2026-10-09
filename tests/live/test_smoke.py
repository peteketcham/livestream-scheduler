"""Opt-in smoke test against a real *test* channel.

Run with:  LSS_LIVE_TEST=1 LSS_LIVE_STATE=<state dir with token.json> \
           LSS_LIVE_CLIENT=<client json> uv run pytest -m live tests/live

It creates, updates and deletes one private broadcast 2 days in the future, then cleans up.
Never point it at the production channel.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import pytest

from livestream_scheduler import auth
from livestream_scheduler.timeutil import utcnow
from livestream_scheduler.youtube.port import BroadcastSpec

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("LSS_LIVE_TEST") != "1", reason="set LSS_LIVE_TEST=1"),
]


def test_create_update_delete_round_trip() -> None:
    from livestream_scheduler.youtube.google_adapter import GoogleYouTube

    state = Path(os.environ["LSS_LIVE_STATE"])
    creds = auth.load_credentials(state)
    assert creds is not None, "run `connect` for the test channel first"
    yt = GoogleYouTube(creds)
    channel = yt.whoami()
    assert channel.handle != "@minnehahaumc", "refusing to run the smoke test on production"

    start = (utcnow() + timedelta(days=2)).replace(minute=0, second=0)
    spec = BroadcastSpec(
        title="livestream-scheduler smoke test",
        description="Created by tests/live/test_smoke.py; safe to delete.",
        start_utc=start,
        end_utc=start + timedelta(hours=1),
        privacy="private",
    )
    b = yt.insert_broadcast(spec)
    try:
        assert yt.get_broadcasts([b.id])[b.id].managed_hash() == spec.managed_hash()
        from dataclasses import replace

        renamed = replace(spec, title="livestream-scheduler smoke (updated)")
        assert yt.update_broadcast(b.id, renamed).title == renamed.title
        assert b.id in [x.id for x in yt.list_upcoming()]
    finally:
        yt.delete_broadcast(b.id)
    assert b.id not in yt.get_broadcasts([b.id])
