"""Research R7 — removal safety rules, at the planner level."""

from __future__ import annotations

from tests.unit.sync.test_planner_updates import _plan, desired, recorded


def _scheduled(n: int):  # type: ignore[no-untyped-def]
    return [recorded(i + 1, desired(f"k{i}", 3 + i)) for i in range(n)]


def test_feed_not_ok_plans_no_removals() -> None:
    p = _plan([], _scheduled(3), feed_ok=False)
    assert p.deletes == [] and p.hold_reason is None


def test_more_than_max_removals_is_held() -> None:
    rs = _scheduled(8)
    keep = [desired("k0", 3), desired("k1", 4)]
    p = _plan(keep, rs)  # 6 removals > 5
    assert p.deletes == [] and p.held_removals == 6
    assert "held for safety" in (p.hold_reason or "")


def test_mass_removal_allowed_when_explicit() -> None:
    p = _plan([], _scheduled(8), allow_mass_removal=True)
    assert len(p.deletes) == 8 and p.hold_reason is None


def test_removing_all_of_two_or_more_is_held() -> None:
    p = _plan([], _scheduled(2))
    assert p.deletes == [] and p.held_removals == 2


def test_removing_the_only_one_is_allowed() -> None:
    p = _plan([], _scheduled(1))
    assert len(p.deletes) == 1
