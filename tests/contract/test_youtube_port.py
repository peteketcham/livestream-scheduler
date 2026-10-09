"""Contract tests every YouTubePort implementation must pass (contracts/youtube-port.md)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from livestream_scheduler.youtube.fake import FakeYouTube
from livestream_scheduler.youtube.port import (
    BroadcastNotFoundError,
    BroadcastSpec,
    YouTubePort,
)

START = datetime(2026, 10, 18, 14, 30, tzinfo=UTC)

SPEC = BroadcastSpec(
    title="October 18th, 2026 - Twenty-First Sunday after Pentecost",
    description="Welcome!\n\nLine two with trailing space: \nhttps://www.minnehaha.org",
    start_utc=START,
    end_utc=START + timedelta(minutes=75),
    privacy="public",
)

ADAPTERS: dict[str, Callable[[], YouTubePort]] = {"fake": FakeYouTube}

try:  # GoogleYouTube joins once its recorded-HTTP fixtures exist (T031).
    from tests.contract.google_fixtures import google_adapter_factory

    ADAPTERS["google"] = google_adapter_factory
except ImportError:  # pragma: no cover
    pass


@pytest.fixture(params=sorted(ADAPTERS))
def yt(request: pytest.FixtureRequest) -> YouTubePort:
    return ADAPTERS[request.param]()


def test_insert_then_get_round_trips_managed_hash(yt: YouTubePort) -> None:
    b = yt.insert_broadcast(SPEC)
    got = yt.get_broadcasts([b.id])
    assert got[b.id].managed_hash() == SPEC.managed_hash()


def test_update_changes_only_managed_fields(yt: YouTubePort) -> None:
    b = yt.insert_broadcast(SPEC)
    if isinstance(yt, FakeYouTube):
        yt.edit_remote(b.id, extra={"thumbnail": "custom.jpg"})
    new = BroadcastSpec(
        title="Renamed",
        description=SPEC.description,
        start_utc=SPEC.start_utc + timedelta(minutes=30),
        end_utc=SPEC.end_utc + timedelta(minutes=30),
        privacy="unlisted",
    )
    updated = yt.update_broadcast(b.id, new)
    assert updated.managed_hash() == new.managed_hash()
    if isinstance(yt, FakeYouTube):
        assert yt.broadcasts[b.id].extra == {"thumbnail": "custom.jpg"}


def test_delete_unknown_raises_not_found(yt: YouTubePort) -> None:
    with pytest.raises(BroadcastNotFoundError):
        yt.delete_broadcast("does-not-exist")


def test_get_after_delete_is_absent(yt: YouTubePort) -> None:
    b = yt.insert_broadcast(SPEC)
    yt.delete_broadcast(b.id)
    assert b.id not in yt.get_broadcasts([b.id])


def test_list_upcoming_only_returns_own_channel() -> None:
    yt = FakeYouTube()
    mine = yt.insert_broadcast(SPEC)
    yt.seed("someone else", START, channel_id="UCother")
    ids = [b.id for b in yt.list_upcoming()]
    assert ids == [mine.id]


def test_list_upcoming_includes_hand_made(yt: YouTubePort) -> None:
    if not isinstance(yt, FakeYouTube):
        pytest.skip("seeding is fake-only")
    hand = yt.seed("October 9th, 2026 - Taizé", datetime(2026, 10, 10, 0, 0, tzinfo=UTC))
    assert hand.id in [b.id for b in yt.list_upcoming()]


def test_quota_accounting(yt: YouTubePort) -> None:
    before = yt.quota_used
    b = yt.insert_broadcast(SPEC)
    yt.get_broadcasts([b.id])
    assert yt.quota_used - before == 51


def test_repr_contains_no_secrets(yt: YouTubePort) -> None:
    text = repr(yt)
    for needle in ("ya29", "refresh_token", "client_secret", "GOCSPX"):
        assert needle not in text
