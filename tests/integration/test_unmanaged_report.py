"""Lost state without a backup: the app never touches or duplicates its old livestreams."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import pytest

from livestream_scheduler import notify
from tests.harness import Env

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

THREE = "\n".join(
    f"BEGIN:VEVENT\nUID:e{i}@t\nDTSTART:2026100{5 + i}T150000Z\nDTEND:2026100{5 + i}T160000Z\n"
    f"SUMMARY:Event {i}\nEND:VEVENT"
    for i in range(3)
)


def test_lost_state_reports_unmanaged_and_creates_nothing(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[EmailMessage] = []
    monkeypatch.setattr(notify, "SENDER", lambda cfg, msg: sent.append(msg))
    env.write_calendar(f"BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:t\n{THREE}\nEND:VCALENDAR\n")
    env.connect_offline()
    env.sync(NOW)
    assert len(env.yt.broadcasts) == 3
    for f in env.state.glob("state.db*"):
        f.unlink()  # disk failure, no backup
    env.connect_offline()
    report = env.sync(NOW + timedelta(hours=1), after_run=notify.after_run)
    assert report.counts["created"] == 0
    assert len(env.yt.broadcasts) == 3
    status = env.cli("status", now=NOW + timedelta(hours=1))
    assert "3 upcoming livestreams on the channel are not managed (no record)" in status.output
    unmanaged = [m for m in sent if "not managed" in str(m["Subject"])]
    assert len(unmanaged) == 1
    env.sync(NOW + timedelta(hours=2), after_run=notify.after_run)
    assert len([m for m in sent if "not managed" in str(m["Subject"])]) == 1
