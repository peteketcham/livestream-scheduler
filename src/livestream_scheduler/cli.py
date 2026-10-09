"""Command-line interface (contracts/cli.md)."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any

import click

from . import paths
from .config import Config, ConfigError, load_config
from .logging import setup_logging


class ExitCode(IntEnum):
    OK = 0
    PARTIAL = 1
    USAGE = 2
    NOT_CONNECTED = 3
    FEED = 4
    SAFETY_HOLD = 5
    INTERNAL = 10


class CliError(Exception):
    """An error with a user-facing message and a specific exit code."""

    def __init__(self, message: str, code: ExitCode) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class Ctx:
    config_path: Path
    state_dir: Path
    json: bool
    _config: Config | None = None
    _warnings: list[str] | None = None

    def config(self) -> Config:
        if self._config is None:
            try:
                self._config, self._warnings = load_config(self.config_path)
            except ConfigError as e:
                raise CliError(str(e), ExitCode.USAGE) from None
        return self._config

    def warnings(self) -> list[str]:
        self.config()
        return self._warnings or []


def emit(ctx: Ctx, human: str, data: dict[str, Any]) -> None:
    if ctx.json:
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        click.echo(human)


@click.group()
@click.option("--config", "config_opt", default=None, help="Path to config.yaml")
@click.option("--state-dir", "state_opt", default=None, help="State directory")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output")
@click.option("-v", "--verbose", count=True)
@click.option("-q", "--quiet", is_flag=True)
@click.pass_context
def cli(
    click_ctx: click.Context,
    config_opt: str | None,
    state_opt: str | None,
    as_json: bool,
    verbose: int,
    quiet: bool,
) -> None:
    """Schedule YouTube livestreams from a calendar feed."""
    setup_logging(-1 if quiet else verbose)
    click_ctx.obj = Ctx(
        config_path=paths.config_path(config_opt),
        state_dir=paths.state_dir(state_opt),
        json=as_json,
    )


# ---- injection points (tests replace these) --------------------------------------------------
def _google_factory(creds: Any) -> Any:
    from .youtube.google_adapter import GoogleYouTube

    return GoogleYouTube(creds)


YOUTUBE_FACTORY: Any = _google_factory
CONSENT: Any = None  # callable(client_config, open_browser, port) -> credentials


def _default_after_run(repo: Any, report: Any, cfg: Any) -> None:
    from .notify import after_run

    after_run(repo, report, cfg)


AFTER_RUN: Any = _default_after_run


def _local(dt: Any, tz: str) -> str:
    from zoneinfo import ZoneInfo

    return str(dt.astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M"))


def _repo(ctx: Ctx) -> Any:
    from .db.migrate import open_db
    from .db.repo import Repo

    return Repo(open_db(ctx.state_dir))


# ---- connect / disconnect ----------------------------------------------------------------------
@cli.command()
@click.option("--no-browser", is_flag=True, help="Print the consent URL instead of opening it")
@click.option("--port", type=int, default=None, help="Loopback port (use with an SSH tunnel)")
@click.option("--forget-tracked", is_flag=True, help="Allow switching to a different channel")
@click.pass_obj
def connect(ctx: Ctx, no_browser: bool, port: int | None, forget_tracked: bool) -> None:
    """Authorize the YouTube channel (one-time)."""
    from . import auth

    cfg = ctx.config()
    if no_browser and port is None:
        port = 8765
    repo = _repo(ctx)
    try:
        client = auth.client_config(cfg)
        consent_fn = CONSENT or (
            lambda c, open_browser, port: auth.run_consent(c, open_browser=open_browser, port=port)
        )
        channel = auth.connect(
            cfg,
            repo,
            ctx.state_dir,
            consent=lambda: consent_fn(client, not no_browser, port),
            youtube_for=YOUTUBE_FACTORY,
            forget_tracked=forget_tracked,
        )
    except auth.ConnectError as e:
        raise CliError(str(e), ExitCode(e.code)) from None
    emit(
        ctx,
        f'Connected to channel "{channel.title}" ({channel.id})',
        {"channel_id": channel.id, "title": channel.title, "handle": channel.handle},
    )


@cli.command()
@click.pass_obj
def disconnect(ctx: Ctx) -> None:
    """Revoke access and delete the stored token."""
    from . import auth

    had = auth.disconnect(_repo(ctx), ctx.state_dir)
    emit(ctx, "Disconnected." if had else "Not connected.", {"disconnected": had})


# ---- sync -------------------------------------------------------------------------------------
def _config_commit(config_path: Path) -> str | None:
    head = config_path.parent / ".git" / "HEAD"
    try:
        ref = head.read_text().strip()
        if ref.startswith("ref: "):
            ref = (config_path.parent / ".git" / ref[5:]).read_text().strip()
        return ref[:12]
    except OSError:
        return None


@cli.command()
@click.option("--dry-run", is_flag=True, help="Show what would change; change nothing")
@click.option("--allow-mass-removal", is_flag=True, help="Proceed past the removal safety hold")
@click.option("--trigger", type=click.Choice(["timer", "manual"]), default=None)
@click.pass_obj
def sync(ctx: Ctx, dry_run: bool, allow_mass_removal: bool, trigger: str | None) -> None:
    """Run one reconciliation pass (this is what the systemd timer runs)."""
    import os

    from .sync.run import SyncOptions, run_sync

    cfg = ctx.config()
    for w in ctx.warnings():
        click.echo(f"warning: {w}", err=True)
    trig = trigger or ("timer" if os.environ.get("INVOCATION_ID") else "manual")
    report = run_sync(
        cfg,
        ctx.state_dir,
        youtube_factory=YOUTUBE_FACTORY,
        options=SyncOptions(
            dry_run=dry_run,
            allow_mass_removal=allow_mass_removal,
            trigger=trig,
            config_commit=_config_commit(ctx.config_path),
        ),
        config_dir=ctx.config_path.parent,
        after_run=AFTER_RUN,
    )
    tz = cfg.defaults.timezone
    lines = []
    c = report.counts
    if report.outcome == "skipped_locked":
        lines.append("Another run is in progress; skipped.")
    else:
        prefix = "DRY RUN — would have: " if dry_run else ""
        lines.append(
            f"{prefix}created {c.get('created', 0)}  updated {c.get('updated', 0)}  "
            f"removed {c.get('removed', 0)}  skipped {c.get('skipped', 0)}  "
            f"deferred {c.get('deferred', 0)}  failed {c.get('failed', 0)}"
            + (f"  (run #{report.run_id}, {report.outcome})" if report.run_id else "")
        )
    for it in report.items:
        when = f"{_local(it.start_utc, tz)} {tz}" if it.start_utc else ""
        title = f'"{it.title}"' if it.title else ""
        url = f"→ https://youtu.be/{it.broadcast_id}" if it.broadcast_id else ""
        msg = f"  ({it.message})" if it.message and it.action not in ("create", "update") else ""
        occ = f"#{it.occurrence_id}" if it.occurrence_id else ""
        lines.append(f"{it.action:<9} {occ:<5} {when}  {title}  {url}{msg}".rstrip())
    for w in report.warnings:
        lines.append(f"warning: {w}")
    if report.error_message:
        lines.append(f"{'error' if report.exit_code else 'note'}: {report.error_message}")
    emit(
        ctx,
        "\n".join(lines),
        {
            "run": {
                "id": report.run_id,
                "outcome": report.outcome,
                "dry_run": report.dry_run,
                "counts": report.counts,
                "error_class": report.error_class,
                "error_message": report.error_message,
            },
            "items": [
                {
                    "occurrence_id": i.occurrence_id,
                    "action": i.action,
                    "result": i.result,
                    "broadcast_id": i.broadcast_id,
                    "message": i.message,
                }
                for i in report.items
            ],
        },
    )
    if report.exit_code:
        raise SystemExitCode(report.exit_code)


class SystemExitCode(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


# ---- status -----------------------------------------------------------------------------------
@cli.command()
@click.pass_obj
def status(ctx: Ctx) -> None:
    """Connection, last run, open problems and the next scheduled livestreams."""
    from .timeutil import from_iso, utcnow

    cfg = ctx.config()
    repo = _repo(ctx)
    conn = repo.get_connection()
    run = repo.last_run()
    src = repo.get_calendar_source()
    problems = repo.open_problems()
    upcoming = [o for o in repo.occurrences(("scheduled",)) if from_iso(o.start_utc) > utcnow()][:5]
    tz = cfg.defaults.timezone
    lines = [
        "channel: "
        + (
            f"{conn.channel_title} ({conn.channel_handle}) — {conn.status}"
            if conn
            else "not connected (run `connect`)"
        ),
        f"config:  {ctx.config_path}"
        + (f" @ {commit}" if (commit := _config_commit(ctx.config_path)) else ""),
        f"feed:    last fetched {src.last_fetched_at if src and src.last_fetched_at else 'never'}",
    ]
    if run:
        lines.append(
            f"last run: #{run.id} {run.finished_at or run.started_at} {run.outcome} — created "
            f"{run.created}, updated {run.updated}, removed {run.removed}, deferred "
            f"{run.deferred}, failed {run.failed}"
            + (f" ({run.error_message})" if run.error_message else "")
        )
    else:
        lines.append("last run: never")
    if problems:
        lines.append("open problems:")
        lines.extend(f"  - {p.problem_key}: {p.summary or ''}" for p in problems)
    lines.append("next scheduled:" if upcoming else "next scheduled: none")
    for o in upcoming:
        b = repo.owned_broadcast(o.id)
        url = f"https://youtu.be/{b.broadcast_id}" if b else ""
        lines.append(f"  #{o.id} {_local(from_iso(o.start_utc), tz)}  {o.title}  {url}")
    emit(
        ctx,
        "\n".join(lines),
        {
            "connection": conn.__dict__ if conn else None,
            "last_run": run.__dict__ if run else None,
            "open_problems": [p.__dict__ for p in problems],
            "next": [o.__dict__ for o in upcoming],
        },
    )


# ---- config check -----------------------------------------------------------------------------
@cli.group("config")
def config_group() -> None:
    """Configuration commands."""


@config_group.command("check")
@click.pass_obj
def config_check(ctx: Ctx) -> None:
    """Validate config, fetch + parse the feed, list what would be scheduled (no YouTube)."""
    from .calendar.expand import FeedError, expand
    from .calendar.fetch import fetch_feed
    from .calendar.mapping import all_day_warning, map_instances
    from .sync.planner import window
    from .timeutil import utcnow

    cfg = ctx.config()
    lines = [f"config ok: {ctx.config_path}"]
    lines.extend(f"warning: {w}" for w in ctx.warnings())
    try:
        data = fetch_feed(
            cfg, _repo(ctx), ctx.state_dir, persist=False, config_dir=ctx.config_path.parent
        )
        w_start, w_end = window(utcnow(), cfg.safety.min_lead_minutes, cfg.horizon.days)
        res = expand(data, w_start, w_end, cfg.defaults.timezone)
    except FeedError as e:
        raise CliError(str(e), ExitCode.FEED) from None
    mapped = map_instances(res.instances, cfg)
    tz = cfg.defaults.timezone
    lines.append(f"{len(mapped.desired)} occurrence(s) in the next {cfg.horizon.days} days:")
    for d in mapped.desired:
        flag = f"  FAILS: {d.error}" if d.error else ""
        lines.append(f"  {_local(d.start_utc, tz)}  [{d.visibility}]  {d.title}{flag}")
        lines.extend(f"      warning: {w}" for w in d.warnings)
    lines.extend(f"warning: {all_day_warning(i)}" for i in res.all_day)
    emit(
        ctx,
        "\n".join(lines),
        {
            "occurrences": [
                {
                    "key": d.key,
                    "start": d.start_utc.isoformat(),
                    "title": d.title,
                    "visibility": d.visibility,
                    "error": d.error,
                    "warnings": d.warnings,
                }
                for d in mapped.desired
            ]
        },
    )


# ---- runs / occurrences / notify ---------------------------------------------------------------
@cli.command()
@click.option("--limit", default=10, show_default=True)
@click.option("--run", "run_id", type=int, default=None, help="Show one run's items")
@click.pass_obj
def runs(ctx: Ctx, limit: int, run_id: int | None) -> None:
    """Recent runs, or one run's per-item details."""
    repo = _repo(ctx)

    def counts(r: Any) -> dict[str, int]:
        return {
            k: getattr(r, k)
            for k in ("created", "updated", "removed", "skipped", "deferred", "failed")
        }

    if run_id is not None:
        r = repo.run(run_id)
        if r is None:
            raise CliError(f"no run #{run_id}", ExitCode.USAGE)
        items = repo.items(run_id)
        titles = {o.id: o.title for o in repo.occurrences()}
        lines = [
            f"run #{r.id} {r.started_at} → {r.finished_at} [{r.trigger}] {r.outcome}"
            + (" (dry run)" if r.dry_run else ""),
            "  " + "  ".join(f"{k} {v}" for k, v in counts(r).items()),
        ]
        if r.error_message:
            lines.append(f"  {r.error_message}")
        for i in items:
            title = titles.get(i.occurrence_id or -1, "")
            url = f" https://youtu.be/{i.broadcast_id}" if i.broadcast_id else ""
            lines.append(
                f"  {i.action:<18} {i.result:<8} #{i.occurrence_id or '-'} {title}{url}"
                + (f" — {i.message}" if i.message else "")
            )
        emit(
            ctx,
            "\n".join(lines),
            {
                "run": {
                    "id": r.id,
                    "started_at": r.started_at,
                    "finished_at": r.finished_at,
                    "outcome": r.outcome,
                    "dry_run": bool(r.dry_run),
                    "counts": counts(r),
                    "error_class": r.error_class,
                    "error_message": r.error_message,
                },
                "items": [
                    {
                        "occurrence_id": i.occurrence_id,
                        "action": i.action,
                        "result": i.result,
                        "broadcast_id": i.broadcast_id,
                        "message": i.message,
                    }
                    for i in items
                ],
            },
        )
        return
    rs = repo.runs(limit)
    lines = [
        f"#{r.id:<5} {r.started_at} {r.trigger:<6} {r.outcome or 'running':<14} "
        + " ".join(f"{k[0]}{v}" for k, v in counts(r).items())
        + (" (dry)" if r.dry_run else "")
        + (f"  {r.error_message}" if r.error_message else "")
        for r in rs
    ]
    emit(ctx, "\n".join(lines) or "no runs yet", {"runs": [r.__dict__ for r in rs]})


@cli.command()
@click.option("--state", "states", multiple=True, help="Filter by state (repeatable)")
@click.option("--all", "show_all", is_flag=True, help="Include past/terminal occurrences")
@click.pass_obj
def occurrences(ctx: Ctx, states: tuple[str, ...], show_all: bool) -> None:
    """Occurrences in the horizon with state, reason and livestream link."""
    from zoneinfo import ZoneInfo

    from .timeutil import from_iso, utcnow

    cfg = ctx.config()
    repo = _repo(ctx)
    tz = ZoneInfo(cfg.defaults.timezone)
    rows = repo.occurrences(states or None)
    if not show_all and not states:
        now = utcnow()
        rows = [
            o for o in rows if from_iso(o.start_utc) >= now and o.state not in ("cancelled", "past")
        ]
    out = []
    lines = []
    for o in rows:
        b = repo.owned_broadcast(o.id)
        url = (
            f"https://youtu.be/{b.broadcast_id}"
            if b
            else (
                f"https://youtu.be/{o.external_broadcast_id}" if o.external_broadcast_id else None
            )
        )
        start = from_iso(o.start_utc).astimezone(tz)
        out.append(
            {
                "id": o.id,
                "key": o.key,
                "start": start.isoformat(),
                "title": o.title,
                "visibility": o.visibility,
                "state": o.state,
                "reason": o.state_reason,
                "deferred": o.deferred_reason,
                "broadcast_url": url,
            }
        )
        lines.append(
            f"#{o.id:<4} {start:%Y-%m-%d %H:%M}  {o.visibility:<8} {o.state:<15} {o.title}"
            + (f"  {url}" if url else "")
            + (f"  ({o.state_reason})" if o.state_reason else "")
            + (f"  [deferred: {o.deferred_reason}]" if o.deferred_reason else "")
        )
    emit(ctx, "\n".join(lines) or "no occurrences", {"occurrences": out})


@cli.group("notify")
def notify_group() -> None:
    """Notification commands."""


@notify_group.command("test")
@click.pass_obj
def notify_test(ctx: Ctx) -> None:
    """Send a test email with the configured SMTP settings."""
    from . import notify

    cfg = ctx.config()
    ok = notify.send(
        cfg.notify,
        f"{notify.PREFIX} test message",
        "This is a test from livestream-scheduler. Notifications are working.",
    )
    if not ok:
        raise CliError("could not send the test email (see log)", ExitCode.INTERNAL)
    emit(ctx, f"Test email sent to {cfg.notify.email_to}.", {"sent": True})


# ---- occurrence overrides ---------------------------------------------------------------------
@cli.group("occurrence")
def occurrence_group() -> None:
    """Per-occurrence overrides: skip, unskip, approve, reclaim, retry."""


def _get_occ(repo: Any, occurrence_id: int) -> Any:
    occ = repo.occurrence(occurrence_id)
    if occ is None:
        raise CliError(f"no occurrence #{occurrence_id}", ExitCode.USAGE)
    return occ


@occurrence_group.command("skip")
@click.argument("occurrence_id", type=int)
@click.pass_obj
def occ_skip(ctx: Ctx, occurrence_id: int) -> None:
    """Skip one occurrence; its livestream is removed on the next sync."""
    repo = _repo(ctx)
    occ = _get_occ(repo, occurrence_id)
    with repo.tx():
        repo.update_occurrence(occ.id, local_override="skip")
    emit(ctx, f"#{occ.id} will be skipped on the next sync.", {"id": occ.id, "override": "skip"})


@occurrence_group.command("unskip")
@click.argument("occurrence_id", type=int)
@click.pass_obj
def occ_unskip(ctx: Ctx, occurrence_id: int) -> None:
    """Undo `skip`; the livestream is recreated on the next sync."""
    repo = _repo(ctx)
    occ = _get_occ(repo, occurrence_id)
    with repo.tx():
        values: dict[str, Any] = {"local_override": None}
        if occ.state == "skipped":
            values["state"] = "pending"
        repo.update_occurrence(occ.id, **values)
    emit(ctx, f"#{occ.id} is no longer skipped.", {"id": occ.id, "override": None})


@occurrence_group.command("approve")
@click.argument("occurrence_id", type=int)
@click.pass_obj
def occ_approve(ctx: Ctx, occurrence_id: int) -> None:
    """Approve an occurrence held because it overlaps another livestream."""
    repo = _repo(ctx)
    occ = _get_occ(repo, occurrence_id)
    with repo.tx():
        repo.update_occurrence(
            occ.id,
            local_override="approve_overlap",
            state="pending" if occ.state == "conflict" else occ.state,
        )
    emit(ctx, f"#{occ.id} approved despite the overlap.", {"id": occ.id})


@occurrence_group.command("reclaim")
@click.argument("occurrence_id", type=int)
@click.pass_obj
def occ_reclaim(ctx: Ctx, occurrence_id: int) -> None:
    """Hand an owner_modified/owner_deleted occurrence back to the app."""
    from .sync.executor import RECLAIMED

    repo = _repo(ctx)
    occ = _get_occ(repo, occurrence_id)
    if occ.state not in ("owner_modified", "owner_deleted"):
        raise CliError(
            f"#{occ.id} is {occ.state}, not owner_modified/owner_deleted", ExitCode.USAGE
        )
    with repo.tx():
        b = repo.owned_broadcast(occ.id)
        if occ.state == "owner_modified" and b is not None:
            # Force the next sync to overwrite: stale hash + sentinel.
            repo.update_broadcast(b.broadcast_id, last_written_hash=RECLAIMED)
            repo.update_occurrence(occ.id, state="scheduled", state_reason=None, desired_hash="")
        else:
            repo.update_occurrence(occ.id, state="pending", state_reason=None)
    emit(ctx, f"#{occ.id} is managed by the app again.", {"id": occ.id})


@occurrence_group.command("retry")
@click.argument("occurrence_id", type=int)
@click.pass_obj
def occ_retry(ctx: Ctx, occurrence_id: int) -> None:
    """Move a failed occurrence back to pending."""
    repo = _repo(ctx)
    occ = _get_occ(repo, occurrence_id)
    if occ.state != "failed":
        raise CliError(f"#{occ.id} is {occ.state}, not failed", ExitCode.USAGE)
    with repo.tx():
        repo.update_occurrence(occ.id, state="pending", state_reason=None, desired_hash="")
    emit(ctx, f"#{occ.id} will be retried on the next sync.", {"id": occ.id})


def main(argv: list[str] | None = None) -> None:
    try:
        cli.main(args=argv, standalone_mode=False)
    except CliError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(int(e.code))
    except SystemExitCode as e:
        sys.exit(e.code)
    except click.exceptions.Abort:
        sys.exit(int(ExitCode.USAGE))
    except click.ClickException as e:
        e.show()
        sys.exit(int(ExitCode.USAGE))
    except Exception as e:  # pragma: no cover - last resort
        from .logging import redact

        click.echo(f"internal error: {redact(str(e))}", err=True)
        sys.exit(int(ExitCode.INTERNAL))
    sys.exit(int(ExitCode.OK))
