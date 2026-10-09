"""001 User Story 3 — see what was scheduled and what failed."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from livestream_scheduler.youtube.port import InvalidRequestError
from tests.harness import Env

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def test_us3_1_runs_and_run_detail(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.yt.fail("insert_broadcast", InvalidRequestError("invalidTitle", "bad"))
    report = env.sync(NOW)
    runs = env.cli("runs", now=NOW)
    assert runs.exit_code == 0
    assert f"#{report.run_id}" in runs.output and "partial" in runs.output
    detail = env.cli("runs", "--run", str(report.run_id), now=NOW)
    assert "create" in detail.output
    assert "YouTube rejected the title" in detail.output

    data = json.loads(env.cli("--json", "runs", "--run", str(report.run_id)).output)
    assert data["run"]["outcome"] == "partial"
    assert data["run"]["counts"] == {
        "created": 3,
        "updated": 0,
        "removed": 0,
        "skipped": 0,
        "deferred": 0,
        "failed": 1,
    }
    assert {i["action"] for i in data["items"]} >= {"create", "fail"}


def test_us3_2_revoked_access_is_explained(env: Env) -> None:
    from livestream_scheduler.youtube.port import AuthError

    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.yt.fail("whoami", AuthError("invalid_grant"))
    result = env.cli("sync", now=NOW)
    assert result.exit_code == 3
    assert "run `connect` again" in result.output
    status = env.cli("status", now=NOW)
    assert "needs_reauth" in status.output


def test_occurrences_listing_and_json(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.sync(NOW)
    out = env.cli("occurrences", now=NOW + timedelta(minutes=1))
    assert out.exit_code == 0
    assert out.output.count("scheduled") == 4
    assert "https://youtu.be/fake0001" in out.output
    data = json.loads(env.cli("--json", "occurrences", now=NOW).output)
    first = data["occurrences"][0]
    assert first["start"] == "2026-10-06T19:00:00-05:00"
    assert first["key"] == "weekly-qa@test|2026-10-07T00:00:00Z"
    assert first["broadcast_url"] == "https://youtu.be/fake0001"
    assert first["state"] == "scheduled"


def test_retention_prunes_old_runs(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.sync(NOW)
    env.sync(NOW + timedelta(days=100))
    runs = env.repo().runs(limit=50)
    assert len(runs) == 1
