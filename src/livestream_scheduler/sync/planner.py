"""Pure reconciliation planner: desired × recorded × now → actions (research R7, data-model.md).

No I/O happens here. The executor applies the plan; `external.py` and `recovery.py` adjust
state around it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..calendar.mapping import DesiredOccurrence
from ..db.repo import Broadcast, Occurrence
from ..timeutil import from_iso

# States where the app still tracks the occurrence against the calendar.
OPEN_STATES = ("pending", "creating", "scheduled", "conflict", "failed", "exists_external")
UNMANAGED_STATES = ("owner_modified", "owner_deleted")


@dataclass
class Create:
    desired: DesiredOccurrence
    occurrence_id: int | None  # None → new row


@dataclass
class Update:
    occurrence_id: int
    broadcast_id: str
    desired: DesiredOccurrence


@dataclass
class Delete:
    occurrence_id: int
    broadcast_id: str
    new_state: str  # 'cancelled' | 'skipped'
    reason: str


@dataclass
class Record:
    """A state/field change with no YouTube call."""

    occurrence_id: int | None
    desired: DesiredOccurrence | None
    state: str
    reason: str | None = None
    action: str = "record"  # run_item action name


@dataclass
class Plan:
    deletes: list[Delete] = field(default_factory=list)
    updates: list[Update] = field(default_factory=list)
    creates: list[Create] = field(default_factory=list)
    records: list[Record] = field(default_factory=list)
    refresh: list[tuple[int, DesiredOccurrence]] = field(default_factory=list)
    held_removals: int = 0
    hold_reason: str | None = None

    @property
    def write_count(self) -> int:
        return len(self.deletes) + len(self.updates) + len(self.creates)


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def plan(
    desired: list[DesiredOccurrence],
    recorded: list[Occurrence],
    owned: dict[int, Broadcast],
    *,
    now: datetime,
    window_start: datetime,
    window_end: datetime,
    overlaps_allowed: bool,
    max_removals: int,
    feed_ok: bool = True,
    allow_mass_removal: bool = False,
) -> Plan:
    """Build the plan.

    owned: occurrence_id → the live broadcast this app created for it.
    window_start already includes the minimum lead time.
    """
    p = Plan()
    by_key = {o.key: o for o in recorded}
    desired_sorted = sorted(desired, key=lambda d: (d.start_utc, d.key))
    desired_keys = {d.key for d in desired}

    # 1) Occurrences whose start has passed: frozen as 'past' (no API calls).
    for o in recorded:
        if o.state in (*OPEN_STATES, *UNMANAGED_STATES) and from_iso(o.start_utc) <= now:
            p.records.append(Record(o.id, None, "past", "start time passed", action="past"))
    past_ids = {r.occurrence_id for r in p.records}

    # 2) Desired occurrences.
    # Intervals already claimed on the channel (scheduled by us) — for overlap checks.
    claimed: list[tuple[datetime, datetime, str]] = []
    for d in desired_sorted:
        rec = by_key.get(d.key)
        if rec is not None and rec.state == "scheduled" and rec.id not in past_ids:
            claimed.append((d.start_utc, d.end_utc, d.key))

    for d in desired_sorted:
        rec = by_key.get(d.key)
        if rec is not None and rec.id in past_ids:
            continue
        broadcast = owned.get(rec.id) if rec is not None else None

        if rec is not None and rec.local_override == "skip":
            if broadcast is not None:
                p.deletes.append(
                    Delete(rec.id, broadcast.broadcast_id, "skipped", "skipped by owner")
                )
            elif rec.state != "skipped":
                p.records.append(Record(rec.id, d, "skipped", "skipped by owner", action="skip"))
            continue

        if rec is not None and rec.state in UNMANAGED_STATES:
            p.refresh.append((rec.id, d))  # keep the calendar's view; never touch the broadcast
            continue
        if rec is not None and rec.state == "creating":
            continue  # unresolved crash recovery; leave for recovery.py next run
        if rec is not None and rec.state == "exists_external":
            p.refresh.append((rec.id, d))
            continue

        if rec is not None and rec.state == "scheduled" and broadcast is not None:
            if d.error:
                p.records.append(
                    Record(rec.id, None, "scheduled", f"calendar change ignored: {d.error}", "warn")
                )
            elif d.desired_hash != rec.desired_hash:
                p.updates.append(Update(rec.id, broadcast.broadcast_id, d))
            continue

        # Not on the channel yet: new, pending, conflict, failed, cancelled (reappeared), skipped
        # (unskipped), or scheduled-without-broadcast (repair).
        if d.error:
            if rec is None or rec.state != "failed" or rec.desired_hash != d.desired_hash:
                p.records.append(
                    Record(rec.id if rec else None, d, "failed", d.error, action="fail")
                )
            continue
        if rec is not None and rec.state == "failed" and rec.desired_hash == d.desired_hash:
            continue  # permanent failure; retried only when the event changes or via `retry`

        approved = rec is not None and rec.local_override == "approve_overlap"
        if not (overlaps_allowed or d.allow_overlap or approved):
            clash = next(
                (
                    key
                    for (s, e, key) in claimed
                    if key != d.key and _overlaps(d.start_utc, d.end_utc, s, e)
                ),
                None,
            )
            if clash is not None:
                if rec is None or rec.state != "conflict":
                    p.records.append(
                        Record(
                            rec.id if rec else None,
                            d,
                            "conflict",
                            "overlaps another livestream; approve with `occurrence approve`",
                            action="conflict",
                        )
                    )
                else:
                    p.refresh.append((rec.id, d))
                continue
        claimed.append((d.start_utc, d.end_utc, d.key))
        p.creates.append(Create(d, rec.id if rec else None))

    # 3) Recorded occurrences no longer in the calendar (inside the window only).
    if feed_ok:
        removals: list[Delete] = []
        cancels: list[Record] = []
        for o in recorded:
            if o.key in desired_keys or o.id in past_ids:
                continue
            if o.state not in (*OPEN_STATES, *UNMANAGED_STATES):
                continue
            start = from_iso(o.start_utc)
            if not (window_start <= start <= window_end):
                continue  # imminent or beyond the horizon: leave alone
            b = owned.get(o.id)
            if o.state == "scheduled" and b is not None:
                removals.append(Delete(o.id, b.broadcast_id, "cancelled", "removed from calendar"))
            else:
                cancels.append(Record(o.id, None, "cancelled", "removed from calendar", "cancel"))
        active = sum(1 for o in recorded if o.state == "scheduled" and o.id not in past_ids)
        mass = len(removals) > max_removals or (active >= 2 and len(removals) >= active)
        if removals and mass and not allow_mass_removal:
            p.held_removals = len(removals)
            p.hold_reason = (
                f"{len(removals)} of {active} scheduled livestreams would be removed; held for "
                "safety. Check the calendar feed, then run `sync --allow-mass-removal`."
            )
        else:
            p.deletes.extend(removals)
        p.records.extend(cancels)

    p.creates.sort(key=lambda c: (c.desired.start_utc, c.desired.key))
    return p


def window(now: datetime, min_lead_minutes: int, horizon_days: int) -> tuple[datetime, datetime]:
    return now + timedelta(minutes=min_lead_minutes), now + timedelta(days=horizon_days)
