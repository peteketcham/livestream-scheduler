"""Safety hold (R7), manual-change respect (R6), crash recovery (R5), quota/transient (R8),
and the hand-made-livestream guard (001 FR-017 / 004 S6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from livestream_scheduler.youtube.port import (
    BroadcastSpec,
    InvalidRequestError,
    TransientError,
)
from tests.harness import Env

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


def _weekly(env: Env, n: int, start_day: int = 6) -> None:
    tz = "TZID=America/Chicago"
    events = "\n".join(
        f"BEGIN:VEVENT\nUID:e{i}@test\nDTSTART;{tz}:202610{start_day + i:02d}T190000\n"
        f"DTEND;{tz}:202610{start_day + i:02d}T200000\nSUMMARY:Event {i}\nEND:VEVENT"
        for i in range(n)
    )
    env.write_calendar(f"BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:t\n{events}\nEND:VCALENDAR\n")


# ---- R7 safety hold ---------------------------------------------------------------------------
def test_more_than_five_removals_are_held(env: Env) -> None:
    _weekly(env, 7)
    env.connect_offline()
    env.sync(NOW)
    _weekly(env, 1)  # 6 removals > 5
    report = env.sync(NOW + HOUR)
    assert report.exit_code == 5
    assert "held for safety" in (report.error_message or "")
    assert len(env.yt.broadcasts) == 7
    report = env.sync(NOW + 2 * HOUR, allow_mass_removal=True)
    assert report.exit_code == 0
    assert len(env.yt.broadcasts) == 1


def test_removing_every_active_occurrence_is_held(env: Env) -> None:
    _weekly(env, 3)
    env.connect_offline()
    env.sync(NOW)
    env.use_calendar("empty.ics")
    report = env.sync(NOW + HOUR)
    assert report.exit_code == 5
    assert len(env.yt.broadcasts) == 3


def test_single_removal_is_not_held(env: Env) -> None:
    _weekly(env, 1)
    env.connect_offline()
    env.sync(NOW)
    env.use_calendar("empty.ics")
    assert env.sync(NOW + HOUR).exit_code == 0
    assert env.yt.broadcasts == {}


# ---- R6 manual changes ------------------------------------------------------------------------
def _first(env: Env) -> str:
    return sorted(env.yt.broadcasts.values(), key=lambda b: b.start_utc)[0].id


def test_remote_edit_becomes_owner_modified_and_is_not_overwritten(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.sync(NOW)
    bid = _first(env)
    env.yt.edit_remote(bid, title="Edited in Studio")
    env.write_calendar(
        (env.calendar.read_text()).replace("SUMMARY:Weekly Q&A", "SUMMARY:Weekly Q&A!")
    )
    env.sync(NOW + HOUR)
    assert env.yt.broadcasts[bid].title == "Edited in Studio"
    occ = next(o for o in env.repo().occurrences() if o.state == "owner_modified")
    assert "edited on YouTube by hand" in (occ.state_reason or "")
    # reclaim hands it back: the next run overwrites with the calendar's version
    assert env.cli("occurrence", "reclaim", str(occ.id)).exit_code == 0
    env.sync(NOW + 2 * HOUR)
    assert env.yt.broadcasts[bid].title == "Weekly Q&A!"


def test_remote_delete_becomes_owner_deleted_and_is_never_recreated(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.sync(NOW)
    bid = _first(env)
    del env.yt.broadcasts[bid]
    env.write_calendar(env.calendar.read_text().replace("Ask us anything.", "Bring questions."))
    env.sync(NOW + HOUR)
    for n in range(2, 6):
        env.sync(NOW + n * HOUR)
    assert len(env.yt.broadcasts) == 3
    assert any(o.state == "owner_deleted" for o in env.repo().occurrences())


def test_live_broadcast_is_left_alone(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.sync(NOW)
    bid = _first(env)
    env.yt.edit_remote(bid, life_cycle_status="live")
    env.write_calendar(env.calendar.read_text().replace("Ask us anything.", "Changed."))
    env.sync(NOW + HOUR)
    assert env.yt.broadcasts[bid].description == "Ask us anything."


# ---- R5 crash recovery ------------------------------------------------------------------------
def test_crash_between_insert_and_commit_is_adopted_not_duplicated(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    real_insert = env.yt.insert_broadcast

    def crashing_insert(spec: BroadcastSpec):  # type: ignore[no-untyped-def]
        real_insert(spec)
        raise RuntimeError("power cut")

    env.yt.insert_broadcast = crashing_insert  # type: ignore[method-assign]
    report = env.sync(NOW)
    assert report.exit_code == 10
    assert len(env.yt.broadcasts) == 1
    env.yt.insert_broadcast = real_insert  # type: ignore[method-assign]
    report = env.sync(NOW + HOUR)
    assert len(env.yt.broadcasts) == 4  # 1 adopted + 3 created, no duplicate
    assert len({b.start_utc for b in env.yt.broadcasts.values()}) == 4
    assert {o.state for o in env.repo().occurrences()} == {"scheduled"}


def test_ambiguous_recovery_fails_safely(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    real_insert = env.yt.insert_broadcast

    def crashing_insert(spec: BroadcastSpec):  # type: ignore[no-untyped-def]
        real_insert(spec)
        real_insert(spec)  # two identical broadcasts appear
        raise RuntimeError("crash")

    env.yt.insert_broadcast = crashing_insert  # type: ignore[method-assign]
    env.sync(NOW)
    env.yt.insert_broadcast = real_insert  # type: ignore[method-assign]
    env.sync(NOW + HOUR)
    failed = [o for o in env.repo().occurrences() if o.state == "failed"]
    assert len(failed) == 1
    assert "ambiguous_recovery" in (failed[0].state_reason or "")


# ---- R8 quota / transient / invalid -----------------------------------------------------------
def test_quota_defers_remaining_and_next_run_completes(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.yt.write_limit = 2
    report = env.sync(NOW)
    assert report.exit_code == 1
    assert report.outcome == "partial"
    assert report.counts["created"] == 2 and report.counts["deferred"] == 2
    deferred = [o for o in env.repo().occurrences() if o.deferred_reason == "quota"]
    assert len(deferred) == 2 and {o.state for o in deferred} == {"pending"}
    env.yt.write_limit = None
    report = env.sync(NOW + HOUR)
    assert report.counts["created"] == 2
    assert len(env.yt.broadcasts) == 4


def test_transient_error_defers_one_and_continues(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.yt.fail("insert_broadcast", TransientError("503"))
    report = env.sync(NOW)
    assert report.counts["created"] == 3 and report.counts["deferred"] == 1
    assert any(o.deferred_reason == "transient" for o in env.repo().occurrences())
    env.sync(NOW + HOUR)
    assert len(env.yt.broadcasts) == 4


def test_invalid_request_marks_failed_with_plain_reason(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.yt.fail("insert_broadcast", InvalidRequestError("invalidScheduledStartTime", "bad"))
    report = env.sync(NOW)
    assert report.counts["failed"] == 1
    failed = next(o for o in env.repo().occurrences() if o.state == "failed")
    assert failed.state_reason == "YouTube rejected the start time (it must be in the future)"
    env.sync(NOW + HOUR)  # permanent: not retried until the event changes
    assert len(env.yt.broadcasts) == 3
    assert env.cli("occurrence", "retry", str(failed.id)).exit_code == 0
    env.sync(NOW + 2 * HOUR)
    assert len(env.yt.broadcasts) == 4


# ---- hand-made livestream guard (FR-017) ------------------------------------------------------
TAIZE = (
    "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:t\nBEGIN:VEVENT\nUID:taize@test\n"
    "DTSTART;TZID=America/Chicago:20261009T190000\nDTEND;TZID=America/Chicago:20261009T200500\n"
    "SUMMARY:Taizé\nEND:VEVENT\nEND:VCALENDAR\n"
)


def test_hand_made_livestream_blocks_duplicate_and_is_untouched(env: Env) -> None:
    env.write_calendar(TAIZE)
    env.connect_offline()
    hand = env.yt.seed(
        "October 9th, 2026 - Taizé",
        datetime(2026, 10, 10, 0, 0, tzinfo=UTC),
        description="Welcome … on October 4th, 2026 for the nineteenth Sunday after Pentecost!",
    )
    report = env.sync(NOW)
    assert env.yt.writes == []
    assert [i.action for i in report.items] == ["external_conflict"]
    occ = env.repo().occurrence_by_key("taize@test")
    assert occ is not None
    assert (occ.state, occ.external_broadcast_id) == ("exists_external", hand.id)
    for n in range(1, 4):
        env.sync(NOW + n * HOUR)
    assert env.yt.writes == []
    assert env.yt.broadcasts[hand.id] == hand

    del env.yt.broadcasts[hand.id]  # the owner deletes the hand-made one
    report = env.sync(NOW + 5 * HOUR)
    assert report.counts["created"] == 1
    assert env.repo().occurrence_by_key("taize@test").state == "scheduled"  # type: ignore[union-attr]


@pytest.mark.parametrize(("offset", "blocked"), [(15, True), (16, False), (-15, True)])
def test_guard_window_is_fifteen_minutes(env: Env, offset: int, blocked: bool) -> None:
    env.write_calendar(TAIZE)
    env.connect_offline()
    env.yt.seed("hand", datetime(2026, 10, 10, 0, 0, tzinfo=UTC) + timedelta(minutes=offset))
    env.sync(NOW)
    assert (env.yt.writes == []) is blocked
