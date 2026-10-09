"""One reconciliation pass: fetch → expand → map → recover → plan → guard → execute → record."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import auth
from ..calendar.expand import FeedError, expand
from ..calendar.fetch import fetch_feed
from ..calendar.mapping import all_day_warning, map_instances
from ..config import Config
from ..db.migrate import open_db
from ..db.repo import Broadcast, Repo
from ..lock import LockHeldError, run_lock
from ..timeutil import to_iso, utcnow
from ..youtube.port import AuthError, NotEligibleError, YouTubePort
from ..youtube.port import Broadcast as RemoteBroadcast
from . import external
from .executor import Executor, Item, RunAborted, desired_fields
from .planner import Plan, plan, window
from .recovery import recover

log = logging.getLogger(__name__)

EXIT_FOR_CLASS = {"auth": 3, "not_eligible": 3, "feed": 4, "safety_hold": 5, "internal": 10}


@dataclass
class SyncOptions:
    dry_run: bool = False
    allow_mass_removal: bool = False
    trigger: str = "manual"
    config_commit: str | None = None


@dataclass
class SyncReport:
    run_id: int | None = None
    outcome: str = "success"
    exit_code: int = 0
    dry_run: bool = False
    items: list[Item] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    error_class: str | None = None
    error_message: str | None = None
    warnings: list[str] = field(default_factory=list)
    hold_reason: str | None = None
    external: list[tuple[int | None, RemoteBroadcast]] = field(default_factory=list)


YouTubeFactory = Callable[[Any], YouTubePort]
AfterRun = Callable[[Repo, SyncReport, Config], None]


def run_sync(
    cfg: Config,
    state_dir: Path,
    *,
    youtube_factory: YouTubeFactory,
    options: SyncOptions,
    config_dir: Path | None = None,
    session: Any = None,
    after_run: AfterRun | None = None,
) -> SyncReport:
    report = SyncReport(dry_run=options.dry_run)
    try:
        with run_lock(state_dir):
            conn = open_db(state_dir)
            repo = Repo(conn)
            try:
                _sync(cfg, repo, state_dir, youtube_factory, options, config_dir, session, report)
                if after_run is not None and not options.dry_run:
                    after_run(repo, report, cfg)
            finally:
                conn.close()
    except LockHeldError:
        report.outcome = "skipped_locked"
        report.exit_code = 0
        report.error_message = "another run is in progress; skipped"
    return report


def _fail(report: SyncReport, error_class: str, message: str) -> None:
    report.outcome = "failed"
    report.error_class = error_class
    report.error_message = message
    report.exit_code = EXIT_FOR_CLASS.get(error_class, 10)


def _sync(
    cfg: Config,
    repo: Repo,
    state_dir: Path,
    youtube_factory: YouTubeFactory,
    options: SyncOptions,
    config_dir: Path | None,
    session: Any,
    report: SyncReport,
) -> None:
    run_id = repo.start_run(options.trigger, options.dry_run, options.config_commit)
    report.run_id = run_id
    yt: YouTubePort | None = None
    res = None
    try:
        connection = repo.get_connection()
        creds = auth.load_credentials(state_dir)
        if connection is None or creds is None:
            _fail(report, "auth", "Not connected to YouTube: run `livestream-scheduler connect`")
            return
        yt = youtube_factory(creds)
        try:
            channel = yt.whoami()
        except AuthError:
            repo.set_connection_status("needs_reauth", "YouTube access expired or was revoked")
            _fail(report, "auth", "YouTube access expired or was revoked; run `connect` again")
            return
        if channel.id != connection.channel_id:
            repo.set_connection_status("needs_reauth", "token belongs to a different channel")
            _fail(
                report,
                "auth",
                f"The saved login now belongs to {channel.handle}, not "
                f"{connection.channel_handle}; run `connect` again",
            )
            return
        if not options.dry_run:
            repo.touch_verified()

        try:
            data = fetch_feed(
                cfg,
                repo,
                state_dir,
                persist=not options.dry_run,
                session=session,
                config_dir=config_dir,
            )
            now = utcnow()
            w_start, w_end = window(now, cfg.safety.min_lead_minutes, cfg.horizon.days)
            expanded = expand(data, w_start, w_end, cfg.defaults.timezone)
        except FeedError as e:
            _fail(report, "feed", f"{e}. Nothing was changed.")
            return
        report.warnings.extend(all_day_warning(i) for i in expanded.all_day)
        mapped = map_instances(expanded.instances, cfg)
        for d in mapped.desired:
            report.warnings.extend(f'"{d.title}" {to_iso(d.start_utc)}: {w}' for w in d.warnings)

        cache = external.UpcomingCache(yt.list_upcoming)
        if not options.dry_run:
            recover(repo, lambda: yt.list_upcoming() if yt else [], run_id, connection.channel_id)
            external.recheck_existing(repo, cache, now)

        recorded = repo.occurrences()
        owned: dict[int, Broadcast] = {}
        for o in recorded:
            b = repo.owned_broadcast(o.id)
            if b is not None:
                owned[o.id] = b
        p: Plan = plan(
            mapped.desired,
            recorded,
            owned,
            now=now,
            window_start=w_start,
            window_end=w_end,
            overlaps_allowed=cfg.overlaps == "allow",
            max_removals=cfg.safety.max_removals_per_run,
            feed_ok=True,
            allow_mass_removal=options.allow_mass_removal,
        )
        blocked = external.block_duplicates(repo, p, cache)
        for rec, ext in blocked:
            report.external.append((rec.occurrence_id, ext))
            item = Item(
                "external_conflict",
                "ok",
                rec.reason,
                rec.occurrence_id,
                None,
                rec.desired.title if rec.desired else None,
                rec.desired.start_utc if rec.desired else None,
            )
            if not options.dry_run and rec.desired is not None:
                with repo.tx():
                    occ_id = rec.occurrence_id
                    if occ_id is None:
                        occ_id = repo.insert_occurrence(
                            key=rec.desired.key,
                            state="exists_external",
                            first_seen_run_id=run_id,
                            last_seen_run_id=run_id,
                            **desired_fields(rec.desired),
                        )
                    repo.update_occurrence(
                        occ_id,
                        state="exists_external",
                        state_reason=rec.reason,
                        external_broadcast_id=ext.id,
                        external_title=ext.title,
                        external_start_utc=to_iso(ext.start_utc),
                        **desired_fields(rec.desired),
                    )
                    repo.add_item(run_id, "external_conflict", "ok", rec.reason, occ_id)
                item.occurrence_id = occ_id
                report.external[-1] = (occ_id, ext)
            report.items.append(item)

        executor = Executor(
            repo,
            yt,
            run_id=run_id,
            channel_id=connection.channel_id,
            stream_id=cfg.youtube.stream_id,
            dry_run=options.dry_run,
        )
        res = executor.execute(p)
        report.items.extend(res.items)
        if res.aborted is not None:
            _fail(report, res.aborted.error_class, res.aborted.message)
        elif p.hold_reason:
            report.outcome = "partial"
            report.error_class = "safety_hold"
            report.error_message = p.hold_reason
            report.hold_reason = p.hold_reason
            report.exit_code = 5
        elif res.quota_hit:
            report.outcome = "partial"
            report.error_class = "quota"
            report.error_message = (
                f"YouTube daily limit reached; {res.deferred} change(s) will be retried next run."
            )
            report.exit_code = 1
        elif res.deferred or res.failed:
            report.outcome = "partial"
            report.exit_code = 1
    except (RunAborted, NotEligibleError) as e:  # pragma: no cover - defensive
        _fail(report, getattr(e, "error_class", "not_eligible"), str(e))
    except Exception as e:
        log.exception("sync failed")
        _fail(report, "internal", f"internal error: {type(e).__name__}: {e}")
    finally:
        counts = {
            "created": res.created if res else 0,
            "updated": res.updated if res else 0,
            "removed": res.removed if res else 0,
            "skipped": res.skipped if res else 0,
            "deferred": res.deferred if res else 0,
            "failed": res.failed if res else 0,
        }
        report.counts = counts
        if not options.dry_run:
            prune(repo, cfg.retention_days)
        repo.finish_run(
            run_id,
            outcome=report.outcome,
            error_class=report.error_class
            if report.error_class in EXIT_FOR_CLASS or report.error_class == "quota"
            else None,
            error_message=report.error_message,
            quota_units_est=yt.quota_used if yt is not None else 0,
            **counts,
        )


def prune(repo: Repo, retention_days: int) -> None:
    """Delete run history and terminal occurrences older than the retention period."""
    from datetime import timedelta

    cutoff = to_iso(utcnow() - timedelta(days=retention_days))
    with repo.tx():
        old_runs = "SELECT id FROM run WHERE started_at < ?"
        for col in ("first_seen_run_id", "last_seen_run_id"):
            repo.conn.execute(
                f"UPDATE occurrence SET {col} = NULL WHERE {col} IN ({old_runs})", (cutoff,)
            )
        repo.conn.execute("DELETE FROM run WHERE started_at < ?", (cutoff,))
        old = [
            r[0]
            for r in repo.conn.execute(
                "SELECT id FROM occurrence WHERE state IN ('cancelled','skipped','past') "
                "AND start_utc < ?",
                (cutoff,),
            )
        ]
        for occ_id in old:
            repo.conn.execute(
                "DELETE FROM broadcast WHERE occurrence_id = ? "
                "AND (deleted_at IS NOT NULL OR life_cycle_status IS NOT NULL)",
                (occ_id,),
            )
            repo.conn.execute(
                "UPDATE broadcast SET occurrence_id = NULL WHERE occurrence_id = ?", (occ_id,)
            )
            repo.conn.execute("DELETE FROM occurrence WHERE id = ?", (occ_id,))
