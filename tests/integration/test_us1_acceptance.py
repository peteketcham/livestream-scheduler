"""001 User Story 1 — connect a channel and auto-schedule upcoming livestreams."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from livestream_scheduler.youtube.fake import FakeYouTube
from livestream_scheduler.youtube.port import Channel
from tests.harness import Env

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def test_us1_1_every_occurrence_in_horizon_is_created(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    report = env.sync(NOW)
    assert report.exit_code == 0, report.error_message
    assert report.counts["created"] == 4
    broadcasts = sorted(env.yt.broadcasts.values(), key=lambda b: b.start_utc)
    assert [b.start_utc for b in broadcasts] == [
        datetime(2026, 10, 7, 0, 0, tzinfo=UTC) + timedelta(weeks=n) for n in range(4)
    ]
    for b in broadcasts:
        assert b.title == "Weekly Q&A"
        assert b.description == "Ask us anything."
        assert b.privacy == "public"
        assert b.end_utc is not None
        assert b.end_utc - b.start_utc == timedelta(hours=1)
    repo = env.repo()
    assert {o.state for o in repo.occurrences()} == {"scheduled"}
    assert len(repo.owned_broadcast_ids()) == 4


def test_us1_2_not_connected_makes_no_api_calls(env: Env) -> None:
    env.use_calendar("weekly.ics")
    result = env.cli("sync", now=NOW)
    assert result.exit_code == 3
    assert "connect" in result.output
    assert env.yt.calls == []
    assert env.yt.broadcasts == {}


def test_us1_3_wrong_channel_refused_then_right_one_accepted(env: Env) -> None:
    wrong = FakeYouTube(Channel("UCother", "Someone Else", "@someoneelse"))
    result = env.cli("connect", "--no-browser", yt=wrong)
    assert result.exit_code == 3
    assert '"Someone Else" (@someoneelse) is not @minnehahaumc' in result.output
    assert not (env.state / "token.json").exists()

    result = env.cli("connect", "--no-browser")
    assert result.exit_code == 0, result.output
    assert 'Connected to channel "Minnehaha UMC" (UCzwZQ34D3RZEncTf6fAe0hQ)' in result.output
    status = env.cli("status", now=NOW)
    assert "Minnehaha UMC (@minnehahaumc) — connected" in status.output


def test_sync_cli_output_lists_creates(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    result = env.cli("sync", now=NOW)
    assert result.exit_code == 0, result.output
    assert "created 4" in result.output
    assert "2026-10-06 19:00 America/Chicago" in result.output
    assert "→ https://youtu.be/fake0001" in result.output


def test_revoked_access_marks_needs_reauth(env: Env) -> None:
    from livestream_scheduler.youtube.port import AuthError

    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.yt.fail("whoami", AuthError("invalid_grant"))
    report = env.sync(NOW)
    assert report.exit_code == 3
    conn = env.repo().get_connection()
    assert conn is not None and conn.status == "needs_reauth"
    assert env.yt.broadcasts == {}


def test_feed_failure_changes_nothing(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.sync(NOW)
    env.write_calendar("<html>oops</html>")
    report = env.sync(NOW + timedelta(hours=1))
    assert report.exit_code == 4
    assert len(env.yt.broadcasts) == 4
