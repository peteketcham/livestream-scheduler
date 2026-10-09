"""Recover occurrences left in 'creating' by a crash between insert and commit (research R5)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from ..db.repo import Repo
from ..timeutil import from_iso, to_iso, utcnow
from ..youtube.port import Broadcast

SKEW = timedelta(minutes=2)


def recover(
    repo: Repo, list_upcoming: Callable[[], list[Broadcast]], run_id: int, channel_id: str
) -> int:
    """Adopt exactly-matching broadcasts created after the intent; returns recovered count."""
    creating = repo.occurrences(("creating",))
    if not creating:
        return 0
    owned = repo.owned_broadcast_ids()
    upcoming = [b for b in list_upcoming() if b.id not in owned]
    recovered = 0
    for occ in creating:
        intent = from_iso(occ.intent_at) if occ.intent_at else None
        start = from_iso(occ.start_utc)
        matches = [
            b
            for b in upcoming
            if intent is not None
            and b.title == occ.title
            and b.start_utc == start
            and b.published_at >= intent - SKEW
        ]
        with repo.tx():
            if len(matches) == 1:
                b = matches[0]
                repo.insert_broadcast(
                    broadcast_id=b.id,
                    occurrence_id=occ.id,
                    channel_id=channel_id,
                    created_at=to_iso(utcnow()),
                    last_written_hash=b.managed_hash(),
                    last_written_at=to_iso(utcnow()),
                    life_cycle_status=b.life_cycle_status,
                )
                repo.update_occurrence(occ.id, state="scheduled", intent_at=None, state_reason=None)
                repo.add_item(
                    run_id, "adopt", "ok", "recovered after interrupted run", occ.id, b.id
                )
                upcoming.remove(b)
                recovered += 1
            elif len(matches) == 0:
                repo.update_occurrence(occ.id, state="pending", intent_at=None)
            else:
                repo.update_occurrence(
                    occ.id,
                    state="failed",
                    intent_at=None,
                    state_reason="ambiguous_recovery: several matching livestreams found; "
                    "check YouTube Studio for duplicates, then `occurrence retry`",
                )
                repo.add_item(run_id, "fail", "error", "ambiguous_recovery", occ.id)
    return recovered
