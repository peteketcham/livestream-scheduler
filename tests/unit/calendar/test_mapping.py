from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from livestream_scheduler.calendar.expand import Instance, expand
from livestream_scheduler.calendar.mapping import map_instances
from livestream_scheduler.config import Config, parse_config
from tests.conftest import FIXTURES

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def config(**calendar: Any) -> Config:
    cfg, _ = parse_config(
        {
            "calendar": {"path": "x.ics", **calendar},
            "youtube": {"channel_handle": "@minnehahaumc"},
            "notify": {"email_to": "a@b.c", "email_from": "a@b.c", "smtp_host": "h"},
        }
    )
    return cfg


def instances(name: str) -> list[Instance]:
    return expand(
        (FIXTURES / "ics" / name).read_bytes(),
        NOW,
        NOW + timedelta(days=60),
        "America/Chicago",
    ).instances


def inst(**kw: Any) -> Instance:
    start = kw.pop("start", datetime(2026, 10, 11, 14, 30, tzinfo=UTC))
    base: dict[str, Any] = {
        "uid": "u@test",
        "key": "u@test",
        "recurring": False,
        "original_start_utc": None,
        "start": start,
        "end": start + timedelta(hours=1),
        "tz": "America/Chicago",
        "summary": "Title",
        "description": "",
    }
    base.update(kw)
    return Instance(**base)


def test_html_description_directives_and_entities() -> None:
    res = map_instances(instances("html-desc.ics"), config())
    (d,) = res.desired
    assert d.title == "Sunday Worship"
    assert d.visibility == "unlisted"
    assert d.description == (
        "Join us for worship!\nBulletin: here: https://minnehaha.org/documents/Bulletin.pdf\n"
        "Tom & Jerry 3"
    )
    assert any("unknown directive yt.colour" in w for w in d.warnings)
    assert any("removed < or >" in w for w in d.warnings)


def test_title_truncated_to_100_chars_with_warning() -> None:
    res = map_instances([inst(summary="x" * 150)], config())
    (d,) = res.desired
    assert len(d.title) == 100
    assert any("title truncated" in w for w in d.warnings)


def test_empty_title_fails() -> None:
    (d,) = map_instances([inst(summary="   ")], config()).desired
    assert d.error == "Event has no title"


def test_description_capped_at_5000_bytes() -> None:
    (d,) = map_instances([inst(description="é" * 4000)], config()).desired
    assert len(d.description.encode("utf-8")) <= 5000
    assert any("description truncated" in w for w in d.warnings)


def test_missing_end_defaults_to_one_hour() -> None:
    (d,) = map_instances([inst(end=None)], config()).desired
    assert d.end_utc - d.start_utc == timedelta(hours=1)


def test_default_visibility_and_utc_times() -> None:
    (d,) = map_instances([inst()], config()).desired
    assert d.visibility == "public"
    assert d.start_utc.tzinfo == UTC
    assert d.spec().privacy == "public"


def test_include_summary_prefix_filters_and_strips() -> None:
    res = map_instances(instances("include.ics"), config(include={"summary_prefix": "[LIVE] "}))
    assert [d.title for d in res.desired] == ["Sunday Worship"]


def test_include_directive_filter() -> None:
    res = map_instances(instances("include.ics"), config(include={"directive": True}))
    assert [d.title for d in res.desired] == ["Choir concert"]


def test_allow_overlap_directive() -> None:
    (d,) = map_instances([inst(description="yt.allow-overlap: yes")], config()).desired
    assert d.allow_overlap


def test_desired_hash_changes_with_content() -> None:
    a = map_instances([inst()], config()).desired[0]
    b = map_instances([inst(summary="Other")], config()).desired[0]
    assert a.desired_hash != b.desired_hash
    assert a.desired_hash == map_instances([inst()], config()).desired[0].desired_hash
