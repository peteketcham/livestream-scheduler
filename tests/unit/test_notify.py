"""Research R10 — email on problem transitions, deduplicated; never secrets."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import pytest
import responses

from livestream_scheduler import notify
from livestream_scheduler.youtube.port import AuthError
from tests.harness import Env

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[EmailMessage]:
    sent: list[EmailMessage] = []
    monkeypatch.setattr(notify, "SENDER", lambda cfg, msg: sent.append(msg))
    return sent


def _subjects(outbox: list[EmailMessage]) -> list[str]:
    return [str(m["Subject"]) for m in outbox]


def test_auth_failure_emails_once_then_reminds_after_24h_then_resolves(
    env: Env, outbox: list[EmailMessage]
) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.yt.fail("whoami", *[AuthError("invalid_grant")] * 30)
    for n in range(5):
        env.sync(NOW + n * HOUR, after_run=notify.after_run)
    assert _subjects(outbox) == ["[livestream-scheduler] PROBLEM: YouTube access needs renewing"]
    body = outbox[0].get_content()
    assert "livestream-scheduler connect" in body
    env.sync(NOW + 25 * HOUR, after_run=notify.after_run)
    assert len(outbox) == 2  # reminder
    env.yt.errors.clear()
    env.sync(NOW + 26 * HOUR, after_run=notify.after_run)
    assert _subjects(outbox)[-1] == "[livestream-scheduler] RESOLVED: YouTube access needs renewing"
    env.sync(NOW + 27 * HOUR, after_run=notify.after_run)
    assert len(outbox) == 3


def test_safety_hold_and_conflict_notify(env: Env, outbox: list[EmailMessage]) -> None:
    env.write_calendar(
        "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:t\n"
        "BEGIN:VEVENT\nUID:a@t\nDTSTART:20261010T150000Z\nDTEND:20261010T170000Z\n"
        "SUMMARY:Long\nEND:VEVENT\n"
        "BEGIN:VEVENT\nUID:b@t\nDTSTART:20261010T160000Z\nDTEND:20261010T163000Z\n"
        "SUMMARY:Overlapping\nEND:VEVENT\nEND:VCALENDAR\n"
    )
    env.connect_offline()
    env.sync(NOW, after_run=notify.after_run)
    assert any("overlaps another livestream" in s or "Overlapping" in s for s in _subjects(outbox))
    body = outbox[-1].get_content()
    assert "occurrence approve" in body


def test_failed_occurrence_notifies_once(env: Env, outbox: list[EmailMessage]) -> None:
    from livestream_scheduler.youtube.port import InvalidRequestError

    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.yt.fail("insert_broadcast", InvalidRequestError("invalidTitle", "bad"))
    env.sync(NOW, after_run=notify.after_run)
    env.sync(NOW + HOUR, after_run=notify.after_run)
    failed = [s for s in _subjects(outbox) if "could not be scheduled" in s]
    assert len(failed) == 1


def test_emails_contain_no_secrets(env: Env, outbox: list[EmailMessage]) -> None:
    url = "https://calendar.google.com/calendar/ical/x/private-abc/basic.ics"
    env.write_config(calendar={"url": url})
    env.connect_offline()
    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, url, status=503)
        env.sync(NOW, after_run=notify.after_run)
    assert outbox, "feed failure should notify"
    text = "\n".join(m.get_content() + str(m["Subject"]) for m in outbox)
    for needle in ("private-abc", "ya29.", "fake-refresh", "fake-secret", "GOCSPX"):
        assert needle not in text


def test_smtp_failure_is_retried_next_run(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[int] = []

    def flaky(cfg: object, msg: EmailMessage) -> None:
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError("smtp down")

    monkeypatch.setattr(notify, "SENDER", flaky)
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.yt.fail("whoami", AuthError("x"), AuthError("x"))
    env.sync(NOW, after_run=notify.after_run)
    env.sync(NOW + HOUR, after_run=notify.after_run)
    assert len(attempts) == 2
    env.sync(NOW + 2 * HOUR, after_run=notify.after_run)  # recovered → RESOLVED
    assert len(attempts) == 3
