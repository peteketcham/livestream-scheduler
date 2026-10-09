"""Pure planner tests (no DB, no YouTube)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from livestream_scheduler.calendar.mapping import DesiredOccurrence
from livestream_scheduler.db.repo import Broadcast, Occurrence
from livestream_scheduler.sync.planner import plan
from livestream_scheduler.timeutil import to_iso

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
W_START, W_END = NOW + timedelta(minutes=15), NOW + timedelta(days=28)


def desired(key: str, day: int, hours: float = 1, **kw: Any) -> DesiredOccurrence:
    start = datetime(2026, 10, day, 15, 0, tzinfo=UTC)
    return DesiredOccurrence(
        key=key,
        ical_uid=key,
        original_start_utc=None,
        title=kw.pop("title", key),
        description="",
        start_utc=start,
        end_utc=start + timedelta(hours=hours),
        source_tz="America/Chicago",
        visibility="public",
        **kw,
    )


def recorded(oid: int, d: DesiredOccurrence, state: str = "scheduled", **kw: Any) -> Occurrence:
    base: dict[str, Any] = {
        "id": oid,
        "key": d.key,
        "ical_uid": d.ical_uid,
        "original_start_utc": None,
        "title": d.title,
        "description": d.description,
        "start_utc": to_iso(d.start_utc),
        "end_utc": to_iso(d.end_utc),
        "source_tz": d.source_tz,
        "visibility": d.visibility,
        "desired_hash": d.desired_hash,
        "state": state,
        "state_reason": None,
        "deferred_reason": None,
        "attempts": 0,
        "intent_at": None,
        "local_override": None,
        "first_seen_run_id": None,
        "last_seen_run_id": None,
        "updated_at": to_iso(NOW),
        "external_broadcast_id": None,
        "external_title": None,
        "external_start_utc": None,
    }
    base.update(kw)
    return Occurrence(**base)


def owned(oid: int) -> Broadcast:
    return Broadcast(
        f"b{oid}", oid, "UC", to_iso(NOW), "h", to_iso(NOW), None, "created", None, None
    )


def _plan(ds: list[DesiredOccurrence], rs: list[Occurrence], **kw: Any):  # type: ignore[no-untyped-def]
    args: dict[str, Any] = {
        "now": NOW,
        "window_start": W_START,
        "window_end": W_END,
        "overlaps_allowed": False,
        "max_removals": 5,
    }
    args.update(kw)
    return plan(ds, rs, {r.id: owned(r.id) for r in rs if r.state == "scheduled"}, **args)


def test_new_desired_becomes_create_in_start_order() -> None:
    p = _plan([desired("b", 9), desired("a", 5)], [])
    assert [c.desired.key for c in p.creates] == ["a", "b"]


def test_changed_hash_becomes_update_unchanged_is_noop() -> None:
    d = desired("a", 5)
    r = recorded(1, d)
    assert _plan([d], [r]).write_count == 0
    p = _plan([desired("a", 5, title="renamed")], [r])
    assert [u.occurrence_id for u in p.updates] == [1]


def test_gone_from_calendar_becomes_delete() -> None:
    r = recorded(1, desired("a", 5))
    p = _plan([], [r])
    assert [(d.occurrence_id, d.new_state) for d in p.deletes] == [(1, "cancelled")]


def test_imminent_and_beyond_horizon_are_not_removed() -> None:
    soon = desired("soon", 1)
    soon.start_utc = NOW + timedelta(minutes=5)
    soon.end_utc = soon.start_utc + timedelta(hours=1)
    far = desired("far", 5)
    far.start_utc = NOW + timedelta(days=40)
    far.end_utc = far.start_utc + timedelta(hours=1)
    p = _plan([], [recorded(1, soon), recorded(2, far)])
    assert p.deletes == [] and [r for r in p.records if r.state == "cancelled"] == []


def test_past_occurrences_are_frozen() -> None:
    old = desired("old", 1)
    old.start_utc = NOW - timedelta(hours=2)
    p = _plan([], [recorded(1, old)])
    assert [(r.occurrence_id, r.state) for r in p.records] == [(1, "past")]
    assert p.deletes == []


def test_overlap_holds_the_later_one() -> None:
    a, b = desired("a", 5, hours=2), desired("b", 5, hours=1)
    b.start_utc = a.start_utc + timedelta(minutes=30)
    b.end_utc = b.start_utc + timedelta(hours=1)
    p = _plan([a, b], [])
    assert [c.desired.key for c in p.creates] == ["a"]
    assert [(r.desired.key if r.desired else None, r.state) for r in p.records] == [
        ("b", "conflict")
    ]
    assert len(_plan([a, b], [], overlaps_allowed=True).creates) == 2
    b.allow_overlap = True
    assert len(_plan([a, b], []).creates) == 2


def test_approved_overlap_is_created() -> None:
    a, b = desired("a", 5, hours=2), desired("b", 5)
    r = recorded(2, b, state="conflict", local_override="approve_overlap")
    assert [c.desired.key for c in _plan([a, b], [r]).creates] == ["a", "b"]


def test_skip_override_deletes_scheduled() -> None:
    d = desired("a", 5)
    p = _plan([d], [recorded(1, d, local_override="skip")])
    assert [(x.occurrence_id, x.new_state) for x in p.deletes] == [(1, "skipped")]


def test_unmanaged_and_external_are_never_written() -> None:
    d1, d2, d3 = desired("a", 5, title="x"), desired("b", 6, title="y"), desired("c", 7, title="z")
    rs = [
        recorded(1, desired("a", 5), state="owner_modified"),
        recorded(2, desired("b", 6), state="owner_deleted"),
        recorded(3, desired("c", 7), state="exists_external"),
    ]
    p = _plan([d1, d2, d3], rs)
    assert p.write_count == 0
    assert sorted(i for i, _ in p.refresh) == [1, 2, 3]
