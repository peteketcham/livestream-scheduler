"""001 User Story 2 — keep the schedule in sync without duplicates (+ catch-up, dry run)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tests.harness import Env

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


def _ids(env: Env) -> list[str]:
    return sorted(env.yt.broadcasts)


def test_us2_1_thirty_runs_without_changes_make_no_writes(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.sync(NOW)
    writes_after_first = len(env.yt.writes)
    for n in range(1, 31):
        report = env.sync(NOW + n * HOUR)
        assert report.exit_code == 0
        assert report.counts["created"] == 0
    assert len(env.yt.writes) == writes_after_first  # SC-003
    assert len(env.yt.broadcasts) == 4


def test_us2_2_rename_and_move_update_the_same_videos(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.sync(NOW)
    before = _ids(env)
    override = (
        "BEGIN:VEVENT\nUID:weekly-qa@test\n"
        "RECURRENCE-ID;TZID=America/Chicago:20261013T190000\n"
        "DTSTART;TZID=America/Chicago:20261013T193000\n"
        "DTEND;TZID=America/Chicago:20261013T203000\n"
        "SUMMARY:Weekly Q&A (late start)\nDESCRIPTION:Ask us anything.\nEND:VEVENT\n"
    )
    env.write_calendar(
        env.calendar.read_text().replace("END:VCALENDAR", override + "END:VCALENDAR")
    )
    report = env.sync(NOW + HOUR)
    assert report.counts == {**report.counts, "created": 0, "updated": 1, "removed": 0}
    assert _ids(env) == before
    moved = next(b for b in env.yt.broadcasts.values() if b.title == "Weekly Q&A (late start)")
    assert moved.start_utc == datetime(2026, 10, 14, 0, 30, tzinfo=UTC)


def test_us2_3_deleted_instance_removes_only_that_broadcast(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.sync(NOW)
    env.use_calendar("exdate.ics")  # Oct 20 instance removed
    report = env.sync(NOW + HOUR)
    assert report.counts["removed"] == 1
    starts = sorted(b.start_utc for b in env.yt.broadcasts.values())
    assert datetime(2026, 10, 21, 0, 0, tzinfo=UTC) not in starts
    assert len(starts) == 3
    occ = env.repo().occurrence_by_key("weekly-qa@test|2026-10-21T00:00:00Z")
    assert occ is not None and occ.state == "cancelled"


def test_us2_4_hand_made_broadcast_is_never_modified(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    hand = env.yt.seed("Choir rehearsal", datetime(2026, 10, 9, 0, 0, tzinfo=UTC))
    env.sync(NOW)
    env.use_calendar("empty.ics")
    env.sync(NOW + HOUR, allow_mass_removal=True)
    assert env.yt.broadcasts[hand.id] == hand
    assert not [w for w in env.yt.writes if w[1] == hand.id]


def test_skip_and_unskip(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.sync(NOW)
    occ = env.repo().occurrence_by_key("weekly-qa@test|2026-10-14T00:00:00Z")
    assert occ is not None
    assert env.cli("occurrence", "skip", str(occ.id)).exit_code == 0
    report = env.sync(NOW + HOUR)
    assert report.counts["skipped"] == 1
    assert len(env.yt.broadcasts) == 3
    assert env.repo().occurrence(occ.id).state == "skipped"  # type: ignore[union-attr]
    assert env.cli("occurrence", "unskip", str(occ.id)).exit_code == 0
    report = env.sync(NOW + 2 * HOUR)
    assert report.counts["created"] == 1
    assert len(env.yt.broadcasts) == 4


def test_cancelled_event_restored_in_calendar_is_recreated(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.sync(NOW)
    env.use_calendar("exdate.ics")
    env.sync(NOW + HOUR)
    env.use_calendar("weekly.ics")
    report = env.sync(NOW + 2 * HOUR)
    assert report.counts["created"] == 1
    assert len(env.yt.broadcasts) == 4


def test_started_occurrences_become_past_without_api_calls(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.sync(NOW)
    writes = len(env.yt.writes)
    env.sync(NOW + timedelta(days=6))  # first instance has started; Nov 3 enters the horizon
    occ = env.repo().occurrence_by_key("weekly-qa@test|2026-10-07T00:00:00Z")
    assert occ is not None and occ.state == "past"
    created_later = len(env.yt.writes) - writes
    assert ("delete", "fake0001") not in env.yt.writes[writes:]
    assert created_later == 1  # Nov 3 entered the horizon


def test_deletes_run_before_updates_before_creates(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.sync(NOW)
    n = len(env.yt.writes)
    cal = (env.root / "config" / "calendar.ics").read_text()
    cal = cal.replace("SUMMARY:Weekly Q&A", "SUMMARY:Weekly Q and A").replace(
        "RRULE:FREQ=WEEKLY;BYDAY=TU",
        "RRULE:FREQ=WEEKLY;BYDAY=TU\nEXDATE;TZID=America/Chicago:20261020T190000",
    )
    env.write_calendar(cal)
    env.sync(NOW + timedelta(days=7, hours=1))  # Nov 3 enters the horizon too
    ops = [op for op, _ in env.yt.writes[n:]]
    assert ops == sorted(ops, key=["delete", "update", "insert"].index)
    assert ops.count("insert") == 1 and "delete" in ops and "update" in ops


def test_catch_up_after_six_days_down(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.sync(NOW)
    # Down for six days (Nov 3 19:00 CST = Nov 4 01:00 UTC enters the 28-day horizon).
    report = env.sync(NOW + timedelta(days=6))
    assert report.counts["created"] == 1
    assert len(env.yt.broadcasts) == 5
    assert len({b.start_utc for b in env.yt.broadcasts.values()}) == 5  # no duplicates


def test_dry_run_changes_nothing_and_predicts_the_real_run(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    dry = env.sync(NOW, dry_run=True)
    assert env.yt.writes == []
    repo = env.repo()
    assert repo.occurrences() == []
    run = repo.run(dry.run_id or 0)
    assert run is not None and run.dry_run == 1
    real = env.sync(NOW)
    assert dry.counts == real.counts
