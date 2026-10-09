"""stderr logging with secret redaction; journald-friendly when run by systemd."""

from __future__ import annotations

import logging
import os
import re
import sys
from typing import ClassVar, TextIO

_PATTERNS = [
    re.compile(r"ya29\.[A-Za-z0-9_\-.]+"),
    re.compile(r"(refresh_token|access_token)([\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+", re.I),
    re.compile(r"(client_secret)([\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+", re.I),
    re.compile(r"GOCSPX-[A-Za-z0-9_\-]+"),
    re.compile(r"(Authorization:\s*)(Bearer|Basic)\s+\S+", re.I),
    re.compile(r"https?://\S*(/ical/|private-)\S*", re.I),
]

_SYSLOG_PRIORITY = {
    logging.CRITICAL: 2,
    logging.ERROR: 3,
    logging.WARNING: 4,
    logging.INFO: 6,
    logging.DEBUG: 7,
}


def redact(text: str) -> str:
    for secret in RedactingFilter.registered:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    for pat in _PATTERNS:
        if pat.groups >= 2:
            text = pat.sub(lambda m: m.group(1) + m.group(2) + "[REDACTED]", text)
        else:
            text = pat.sub("[REDACTED]", text)
    return text


class RedactingFilter(logging.Filter):
    """Scrubs tokens, client secrets, auth headers, secret calendar URLs and registered values."""

    registered: ClassVar[set[str]] = set()

    @classmethod
    def register(cls, secret: str) -> None:
        if len(secret) >= 4:
            cls.registered.add(secret)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        record.msg = redact(message)
        record.args = None
        return True


class _JournaldFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        prio = _SYSLOG_PRIORITY.get(record.levelno, 6)
        return f"<{prio}>{record.name}: {record.getMessage()}"


def setup_logging(verbosity: int = 0, stream: TextIO | None = None) -> None:
    """verbosity: -1 quiet (warnings), 0 info, 1+ debug."""
    level = logging.WARNING if verbosity < 0 else logging.DEBUG if verbosity > 0 else logging.INFO
    handler = logging.StreamHandler(stream or sys.stderr)
    if os.environ.get("JOURNAL_STREAM"):
        handler.setFormatter(_JournaldFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
            )
        )
    handler.addFilter(RedactingFilter())
    root = logging.getLogger("livestream_scheduler")
    root.handlers[:] = [handler]
    root.setLevel(level)
    root.propagate = False
    # Third-party libraries can log request URLs; route them through the same filter.
    for name in ("googleapiclient", "google_auth_oauthlib", "urllib3"):
        lib = logging.getLogger(name)
        lib.handlers[:] = [handler]
        lib.setLevel(logging.WARNING)
        lib.propagate = False
