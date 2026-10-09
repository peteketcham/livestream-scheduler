"""Never duplicate a livestream created by hand (001 FR-017, 004 research S6).

Livestreams found here are only *read*: their ids never enter the `broadcast` table, so the
ownership rule guarantees they are never updated or deleted.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from ..db.repo import Repo
from ..timeutil import from_iso, to_iso
from ..youtube.port import Broadcast
from .planner import Plan, Record

WINDOW = timedelta(minutes=15)


class UpcomingCache:
    """At most one `list_upcoming` call per run."""

    def __init__(self, fetch: Callable[[], list[Broadcast]]) -> None:
        self._fetch = fetch
        self._value: list[Broadcast] | None = None

    def get(self) -> list[Broadcast]:
        if self._value is None:
            self._value = self._fetch()
        return self._value


def _unowned(repo: Repo, upcoming: list[Broadcast]) -> list[Broadcast]:
    owned = repo.owned_broadcast_ids()
    return [b for b in upcoming if b.id not in owned]


def recheck_existing(repo: Repo, cache: UpcomingCache, now: datetime) -> int:
    """exists_external → pending when the hand-made livestream is gone. Returns count released."""
    rows = repo.occurrences(("exists_external",))
    if not rows:
        return 0
    present = {b.id for b in _unowned(repo, cache.get())}
    released = 0
    with repo.tx():
        for o in rows:
            if o.external_broadcast_id in present:
                continue
            if from_iso(o.start_utc) > now:
                repo.update_occurrence(
                    o.id,
                    state="pending",
                    state_reason=None,
                    external_broadcast_id=None,
                    external_title=None,
                    external_start_utc=None,
                )
                released += 1
    return released


def block_duplicates(
    repo: Repo, plan: Plan, cache: UpcomingCache
) -> list[tuple[Record, Broadcast]]:
    """Turn creates that collide with a hand-made livestream into exists_external records."""
    if not plan.creates:
        return []
    unowned = _unowned(repo, cache.get())
    blocked: list[tuple[Record, Broadcast]] = []
    keep = []
    for c in plan.creates:
        match = next((b for b in unowned if abs(b.start_utc - c.desired.start_utc) <= WINDOW), None)
        if match is None:
            keep.append(c)
            continue
        rec = Record(
            c.occurrence_id,
            c.desired,
            "exists_external",
            f"A livestream created by hand already exists at {to_iso(match.start_utc)}: "
            f'"{match.title}" {match.url}',
            action="external_conflict",
        )
        blocked.append((rec, match))
    plan.creates = keep
    return blocked
