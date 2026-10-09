"""In-memory YouTubePort for tests (and offline experiments)."""

from __future__ import annotations

import itertools
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime

from ..timeutil import utcnow
from .port import (
    QUOTA_COST,
    Broadcast,
    BroadcastNotFoundError,
    BroadcastSpec,
    Channel,
    QuotaExceededError,
    YouTubeError,
)

MINNEHAHA = Channel(id="UCzwZQ34D3RZEncTf6fAe0hQ", title="Minnehaha UMC", handle="@minnehahaumc")

UPCOMING = ("created", "ready", "testing")


class FakeYouTube:
    def __init__(self, channel: Channel = MINNEHAHA) -> None:
        self.channel = channel
        self.broadcasts: dict[str, Broadcast] = {}
        self.quota_used = 0
        self.writes: list[tuple[str, str]] = []  # (op, broadcast_id)
        self.calls: list[str] = []
        self.write_limit: int | None = None  # QuotaExceeded after this many writes
        self.errors: dict[str, list[YouTubeError]] = {}  # op -> errors to raise, in order
        self.before_call: Callable[[str], None] | None = None
        self._ids = (f"fake{n:04d}" for n in itertools.count(1))

    # ---- helpers for tests ----------------------------------------------------------------
    def seed(
        self,
        title: str,
        start_utc: datetime,
        end_utc: datetime | None = None,
        *,
        channel_id: str | None = None,
        description: str = "",
        privacy: str = "public",
        life_cycle_status: str = "created",
        published_at: datetime | None = None,
        broadcast_id: str | None = None,
    ) -> Broadcast:
        """Add a broadcast that was NOT created through this port (e.g. made by hand)."""
        b = Broadcast(
            id=broadcast_id or next(self._ids),
            channel_id=channel_id or self.channel.id,
            title=title,
            description=description,
            start_utc=start_utc,
            end_utc=end_utc,
            privacy=privacy,
            published_at=published_at or utcnow(),
            life_cycle_status=life_cycle_status,
        )
        self.broadcasts[b.id] = b
        return b

    def edit_remote(self, broadcast_id: str, **changes: object) -> None:
        """Simulate an owner edit in YouTube Studio."""
        self.broadcasts[broadcast_id] = replace(self.broadcasts[broadcast_id], **changes)  # type: ignore[arg-type]

    def fail(self, op: str, *errors: YouTubeError) -> None:
        self.errors.setdefault(op, []).extend(errors)

    # ---- port -----------------------------------------------------------------------------
    def _call(self, op: str, cost_key: str) -> None:
        self.calls.append(op)
        if self.before_call:
            self.before_call(op)
        if self.errors.get(op):
            raise self.errors[op].pop(0)
        if (
            cost_key != "list"
            and self.write_limit is not None
            and len(self.writes) >= self.write_limit
        ):
            raise QuotaExceededError("quotaExceeded")
        self.quota_used += QUOTA_COST[cost_key]

    def whoami(self) -> Channel:
        self._call("whoami", "list")
        return self.channel

    def get_broadcasts(self, ids: Sequence[str]) -> dict[str, Broadcast]:
        result: dict[str, Broadcast] = {}
        for i in range(0, len(ids), 50):
            self._call("get_broadcasts", "list")
            for bid in ids[i : i + 50]:
                b = self.broadcasts.get(bid)
                if b is not None and b.channel_id == self.channel.id:
                    result[bid] = b
        return result

    def list_upcoming(self, since: datetime | None = None) -> list[Broadcast]:
        self._call("list_upcoming", "list")
        return sorted(
            (
                b
                for b in self.broadcasts.values()
                if b.channel_id == self.channel.id
                and b.life_cycle_status in UPCOMING
                and (since is None or b.published_at >= since or b.start_utc >= since)
            ),
            key=lambda b: (b.start_utc, b.id),
        )

    def insert_broadcast(self, spec: BroadcastSpec) -> Broadcast:
        self._call("insert_broadcast", "insert")
        b = Broadcast(
            id=next(self._ids),
            channel_id=self.channel.id,
            title=spec.title,
            description=spec.description,
            start_utc=spec.start_utc,
            end_utc=spec.end_utc,
            privacy=spec.privacy,
            published_at=utcnow(),
            life_cycle_status="created",
            made_for_kids=spec.made_for_kids,
            auto_start=spec.auto_start,
            auto_stop=spec.auto_stop,
            dvr=spec.dvr,
        )
        self.broadcasts[b.id] = b
        self.writes.append(("insert", b.id))
        return b

    def update_broadcast(self, broadcast_id: str, spec: BroadcastSpec) -> Broadcast:
        self._call("update_broadcast", "update")
        current = self.broadcasts.get(broadcast_id)
        if current is None or current.channel_id != self.channel.id:
            raise BroadcastNotFoundError(broadcast_id)
        b = replace(
            current,
            title=spec.title,
            description=spec.description,
            start_utc=spec.start_utc,
            end_utc=spec.end_utc,
            privacy=spec.privacy,
            made_for_kids=spec.made_for_kids,
            auto_start=spec.auto_start,
            auto_stop=spec.auto_stop,
            dvr=spec.dvr,
        )
        self.broadcasts[broadcast_id] = b
        self.writes.append(("update", broadcast_id))
        return b

    def delete_broadcast(self, broadcast_id: str) -> None:
        self._call("delete_broadcast", "delete")
        current = self.broadcasts.get(broadcast_id)
        if current is None or current.channel_id != self.channel.id:
            raise BroadcastNotFoundError(broadcast_id)
        del self.broadcasts[broadcast_id]
        self.writes.append(("delete", broadcast_id))

    def bind(self, broadcast_id: str, stream_id: str) -> None:
        self._call("bind", "bind")
        if broadcast_id not in self.broadcasts:
            raise BroadcastNotFoundError(broadcast_id)
        b = self.broadcasts[broadcast_id]
        self.broadcasts[broadcast_id] = replace(b, extra={**b.extra, "boundStreamId": stream_id})
        self.writes.append(("bind", broadcast_id))

    def __repr__(self) -> str:
        return f"FakeYouTube(channel={self.channel.handle}, broadcasts={len(self.broadcasts)})"
