from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from livestream_scheduler.calendar.expand import FeedError, expand
from tests.conftest import FIXTURES

ICS = FIXTURES / "ics"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
START = NOW + timedelta(minutes=15)
END = NOW + timedelta(days=28)


def _expand(name: str, start: datetime = START, end: datetime = END):  # type: ignore[no-untyped-def]
    return expand((ICS / name).read_bytes(), start, end, "America/Chicago")


def test_weekly_keys_use_uid_and_original_start_utc() -> None:
    res = _expand("weekly.ics")
    assert [i.key for i in res.instances] == [
        "weekly-qa@test|2026-10-07T00:00:00Z",
        "weekly-qa@test|2026-10-14T00:00:00Z",
        "weekly-qa@test|2026-10-21T00:00:00Z",
        "weekly-qa@test|2026-10-28T00:00:00Z",
    ]
    assert all(i.recurring for i in res.instances)
    assert res.instances[0].start.astimezone(UTC) == datetime(2026, 10, 7, 0, 0, tzinfo=UTC)
    assert res.instances[0].tz == "America/Chicago"


def test_moved_instance_keeps_its_key() -> None:
    res = _expand("overrides.ics")
    moved = next(i for i in res.instances if i.key == "weekly-qa@test|2026-10-14T00:00:00Z")
    assert moved.start.astimezone(UTC) == datetime(2026, 10, 14, 0, 30, tzinfo=UTC)
    assert moved.summary == "Weekly Q&A (late start)"
    assert len(res.instances) == 4


def test_exdate_is_excluded() -> None:
    keys = [i.key for i in _expand("exdate.ics").instances]
    assert "weekly-qa@test|2026-10-21T00:00:00Z" not in keys
    assert len(keys) == 3


def test_local_time_kept_across_dst() -> None:
    res = _expand(
        "dst.ics",
        datetime(2026, 10, 20, tzinfo=UTC),
        datetime(2027, 3, 31, tzinfo=UTC),
    )
    utc_starts = [i.start.astimezone(UTC) for i in res.instances]
    assert utc_starts == [
        datetime(2026, 10, 25, 14, 30, tzinfo=UTC),  # CDT
        datetime(2026, 11, 1, 15, 30, tzinfo=UTC),  # CST (DST ended that morning)
        datetime(2026, 11, 8, 15, 30, tzinfo=UTC),
        datetime(2027, 3, 7, 15, 30, tzinfo=UTC),  # CST
        datetime(2027, 3, 14, 14, 30, tzinfo=UTC),  # CDT (DST began that morning)
    ]
    assert all(i.start.hour == 9 and i.start.minute == 30 for i in res.instances)


def test_single_event_key_is_uid_and_floating_uses_default_tz() -> None:
    res = _expand("floating.ics")
    floating = next(i for i in res.instances if i.uid == "floating@test")
    assert floating.key == "floating@test"
    assert not floating.recurring
    assert floating.original_start_utc is None
    assert floating.start.astimezone(UTC) == datetime(2026, 10, 15, 23, 0, tzinfo=UTC)
    assert floating.end is not None
    assert floating.end - floating.start == timedelta(minutes=90)


def test_missing_end_is_none() -> None:
    noend = next(i for i in _expand("floating.ics").instances if i.uid == "noend@test")
    assert noend.end is None


def test_all_day_events_are_reported_separately() -> None:
    res = _expand("allday.ics")
    assert [i.uid for i in res.instances] == ["timed@test"]
    assert [i.uid for i in res.all_day] == ["allday@test"]


def test_cancelled_instances_are_excluded() -> None:
    assert "d@test" not in [i.uid for i in _expand("include.ics").instances]


def test_window_excludes_instances_before_min_lead() -> None:
    res = _expand("weekly.ics", start=datetime(2026, 10, 7, 0, 1, tzinfo=UTC))
    assert res.instances[0].key == "weekly-qa@test|2026-10-14T00:00:00Z"


def test_empty_calendar_is_valid() -> None:
    res = _expand("empty.ics")
    assert res.instances == []
    assert res.event_count == 0


def test_garbage_raises_feed_error() -> None:
    with pytest.raises(FeedError):
        expand(b"<html>not a calendar</html>", START, END, "America/Chicago")
