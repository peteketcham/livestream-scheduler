from __future__ import annotations

import io
import logging

import pytest

from livestream_scheduler.logging import RedactingFilter, setup_logging


def _capture(monkeypatch: pytest.MonkeyPatch, journald: bool) -> tuple[logging.Logger, io.StringIO]:
    if journald:
        monkeypatch.setenv("JOURNAL_STREAM", "8:12345")
    else:
        monkeypatch.delenv("JOURNAL_STREAM", raising=False)
    buf = io.StringIO()
    setup_logging(verbosity=0, stream=buf)
    return logging.getLogger("livestream_scheduler.test"), buf


@pytest.mark.parametrize(
    "secret",
    [
        "ya29.a0AfH6SMBx-very_secret.token",
        "refresh_token=1//0gAbCdEf",
        '"client_secret": "GOCSPX-abcdef123"',
        "Authorization: Bearer abc.def.ghi",
        "https://calendar.google.com/calendar/ical/abc%40group/private-123/basic.ics",
    ],
)
def test_secrets_are_redacted(monkeypatch: pytest.MonkeyPatch, secret: str) -> None:
    log, buf = _capture(monkeypatch, journald=False)
    log.warning("value is %s", secret)
    out = buf.getvalue()
    assert "[REDACTED]" in out
    for fragment in ("ya29.a0", "1//0gAbCdEf", "GOCSPX-abcdef123", "abc.def.ghi", "private-123"):
        assert fragment not in out


def test_registered_secret_values_are_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    log, buf = _capture(monkeypatch, journald=False)
    RedactingFilter.register("hunter2-smtp-pass")
    log.error("login failed with hunter2-smtp-pass")
    assert "hunter2-smtp-pass" not in buf.getvalue()


def test_journald_mode_has_priority_prefix_and_no_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log, buf = _capture(monkeypatch, journald=True)
    log.warning("hello")
    line = buf.getvalue().strip()
    assert line.startswith("<4>")
    assert "hello" in line
    assert not any(ch.isdigit() for ch in line.split("hello")[0][3:])


def test_human_mode_has_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    log, buf = _capture(monkeypatch, journald=False)
    log.warning("hello")
    assert buf.getvalue()[:4].isdigit()
