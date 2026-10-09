"""Owner notifications by email (research R10): on problem transitions, deduplicated."""

from __future__ import annotations

import logging
import smtplib
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from email.message import EmailMessage
from typing import Any

from .config import Config, NotifyConfig
from .db.repo import Repo
from .logging import redact
from .secrets import resolve
from .timeutil import from_iso, to_iso, utcnow

log = logging.getLogger(__name__)

PREFIX = "[livestream-scheduler]"

RUN_PROBLEMS: dict[str, tuple[str, str]] = {
    # error_class: (short title, what to do)
    "auth": (
        "YouTube access needs renewing",
        "Run `livestream-scheduler connect` (on the server: `lss connect --no-browser --port "
        "8765` through an SSH tunnel) and choose the Minnehaha UMC channel.",
    ),
    "not_eligible": (
        "Channel cannot live stream",
        "In YouTube Studio, enable live streaming for the channel (it can take 24 hours).",
    ),
    "feed": (
        "Calendar feed unavailable",
        "Check that the calendar's secret address (credential `calendar-url`) is still valid. "
        "Nothing on YouTube was changed.",
    ),
    "safety_hold": (
        "Removals held for safety",
        "Check the calendar. If the removals are intended, run "
        "`livestream-scheduler sync --allow-mass-removal`.",
    ),
    "quota": (
        "YouTube daily limit reached",
        "Nothing to do: remaining changes are retried automatically on later runs.",
    ),
    "internal": (
        "Internal error",
        "See `journalctl -u livestream-scheduler` for details.",
    ),
}


def _smtp_send(cfg: NotifyConfig, msg: EmailMessage) -> None:
    password = resolve(cfg.smtp_password) if cfg.smtp_password is not None else None
    context = ssl.create_default_context()
    if cfg.smtp_security == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, context=context)
    else:
        server = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30)
    with server:
        if cfg.smtp_security == "starttls":
            server.starttls(context=context)
        if cfg.smtp_user and password:
            server.login(cfg.smtp_user, password)
        server.send_message(msg)


SENDER: Callable[[NotifyConfig, EmailMessage], None] = _smtp_send


@dataclass
class Problem:
    key: str
    title: str
    body: str
    one_shot: bool = False


def build_message(cfg: NotifyConfig, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = redact(subject)
    msg["From"] = cfg.email_from
    msg["To"] = cfg.email_to
    msg.set_content(redact(body))
    return msg


def send(cfg: NotifyConfig, subject: str, body: str) -> bool:
    try:
        SENDER(cfg, build_message(cfg, subject, body))
        return True
    except Exception as e:
        log.warning("could not send notification email: %s", redact(str(e)))
        return False


def _context(repo: Repo, report: Any) -> str:
    conn = repo.get_connection()
    channel = f"{conn.channel_title} ({conn.channel_handle})" if conn else "not connected"
    return f"Channel: {channel}\nRun: #{report.run_id} ({report.outcome})\n"


def current_problems(repo: Repo, report: Any) -> list[Problem]:
    problems: list[Problem] = []
    ctx = _context(repo, report)
    if report.error_class in RUN_PROBLEMS:
        title, fix = RUN_PROBLEMS[report.error_class]
        problems.append(
            Problem(
                report.error_class,
                title,
                f"{ctx}\nWhat happened: {report.error_message}\n\nWhat to do: {fix}\n",
            )
        )
    for o in repo.occurrences(("failed", "conflict")):
        if o.state == "failed":
            title = f'"{o.title}" could not be scheduled'
            fix = f"Fix the calendar event, or run `livestream-scheduler occurrence retry {o.id}`."
        else:
            title = f'"{o.title}" overlaps another livestream'
            fix = f"If both are intended, run `livestream-scheduler occurrence approve {o.id}`."
        problems.append(
            Problem(
                f"occurrence:{o.id}:{o.state}",
                title,
                f"{ctx}\nOccurrence #{o.id}: {o.title} at {o.start_utc} UTC\n"
                f"Reason: {o.state_reason}\n\nWhat to do: {fix}\n",
            )
        )
    for occ_id, b in getattr(report, "external", []):
        occ = repo.occurrence(occ_id) if occ_id else None
        name = occ.title if occ else b.title
        problems.append(
            Problem(
                f"external:{occ_id}",
                f"Already on the channel: {name}",
                f'{ctx}\nThe calendar event "{name}" matches a livestream that was created by '
                f'hand: "{b.title}" at {to_iso(b.start_utc)} UTC — {b.url}\n\n'
                "No duplicate was created; nothing was changed. If you delete the hand-made "
                "livestream, the app will schedule its own on the next run.\n",
                one_shot=True,
            )
        )
    return problems


def after_run(repo: Repo, report: Any, cfg: Config) -> None:
    """Called after every real (non-dry) run."""
    if report.outcome == "skipped_locked":
        return
    ncfg = cfg.notify
    now = utcnow()
    remind = timedelta(hours=ncfg.reminder_hours)
    active = current_problems(repo, report)
    active_keys = {p.key for p in active}

    for p in active:
        row = repo.notification(p.key)
        if p.one_shot:
            if row is not None:
                continue
            if send(ncfg, f"{PREFIX} {p.title}", p.body):
                with repo.tx():
                    repo.upsert_notification(
                        p.key, summary=p.title, last_sent_at=to_iso(now), resolved_at=to_iso(now)
                    )
            continue
        if row is None or row.resolved_at is not None:
            with repo.tx():
                if row is None:
                    repo.upsert_notification(p.key, summary=p.title)
                else:
                    repo.reopen_notification(p.key, p.title)
            due = True
        else:
            due = row.last_sent_at is None or now - from_iso(row.last_sent_at) >= remind
        if due and send(ncfg, f"{PREFIX} PROBLEM: {p.title}", p.body):
            with repo.tx():
                repo.upsert_notification(p.key, last_sent_at=to_iso(now))

    # Resolve problems that cleared. Run-level problems clear only on a run that got far
    # enough to tell (any non-failed run, or a failure of a different class).
    for row in repo.open_problems():
        if row.problem_key in active_keys or row.problem_key.startswith("external:"):
            continue
        if row.problem_key in RUN_PROBLEMS and report.outcome not in ("success", "partial"):
            continue  # a failed run cannot tell whether other run-level problems cleared
        sent_before = row.last_sent_at is not None
        if not sent_before or send(
            ncfg,
            f"{PREFIX} RESOLVED: {row.summary}",
            f"{_context(repo, report)}\nResolved: {row.summary}\n",
        ):
            with repo.tx():
                repo.upsert_notification(row.problem_key, resolved_at=to_iso(now))
