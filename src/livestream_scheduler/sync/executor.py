"""Apply a Plan via YouTubePort with the safety rules of research R5, R6 and R8."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..calendar.mapping import DesiredOccurrence
from ..db.repo import Occurrence, Repo
from ..timeutil import to_iso, utcnow
from ..youtube.port import (
    AuthError,
    Broadcast,
    BroadcastNotFoundError,
    InvalidRequestError,
    NotEligibleError,
    QuotaExceededError,
    TransientError,
    YouTubePort,
)
from .planner import Create, Delete, Plan, Update

log = logging.getLogger(__name__)

MANAGEABLE_LIFECYCLE = ("created", "ready")
# Set by `occurrence reclaim`: the next write may overwrite whatever is on YouTube.
RECLAIMED = "reclaimed"

REASONS = {
    "invalidScheduledStartTime": "YouTube rejected the start time (it must be in the future)",
    "invalidScheduledEndTime": "YouTube rejected the end time",
    "invalidTitle": "YouTube rejected the title",
    "invalidDescription": "YouTube rejected the description",
    "invalidPrivacyStatus": "YouTube rejected the visibility setting",
}


class RunAborted(Exception):
    def __init__(self, error_class: str, message: str) -> None:
        super().__init__(message)
        self.error_class = error_class
        self.message = message


@dataclass
class Item:
    action: str
    result: str  # ok | deferred | error
    message: str | None = None
    occurrence_id: int | None = None
    broadcast_id: str | None = None
    title: str | None = None
    start_utc: datetime | None = None


@dataclass
class ExecResult:
    items: list[Item] = field(default_factory=list)
    created: int = 0
    updated: int = 0
    removed: int = 0
    skipped: int = 0
    deferred: int = 0
    failed: int = 0
    quota_hit: bool = False
    aborted: RunAborted | None = None


def desired_fields(d: DesiredOccurrence) -> dict[str, Any]:
    return {
        "ical_uid": d.ical_uid,
        "original_start_utc": d.original_start_iso,
        "title": d.title,
        "description": d.description,
        "start_utc": to_iso(d.start_utc),
        "end_utc": to_iso(d.end_utc),
        "source_tz": d.source_tz,
        "visibility": d.visibility,
        "desired_hash": d.desired_hash,
    }


class Executor:
    def __init__(
        self,
        repo: Repo,
        yt: YouTubePort,
        *,
        run_id: int,
        channel_id: str,
        stream_id: str | None = None,
        dry_run: bool = False,
    ) -> None:
        self.repo = repo
        self.yt = yt
        self.run_id = run_id
        self.channel_id = channel_id
        self.stream_id = stream_id
        self.dry_run = dry_run
        self.res = ExecResult()
        self._stop_writes = False

    # ---- bookkeeping --------------------------------------------------------------------
    def _item(self, item: Item) -> None:
        self.res.items.append(item)
        if not self.dry_run:
            self.repo.add_item(
                self.run_id,
                item.action,
                item.result,
                item.message,
                item.occurrence_id,
                item.broadcast_id,
            )

    def _ensure_row(self, occurrence_id: int | None, d: DesiredOccurrence, state: str) -> int:
        if occurrence_id is not None:
            return occurrence_id
        return self.repo.insert_occurrence(
            key=d.key,
            state=state,
            first_seen_run_id=self.run_id,
            last_seen_run_id=self.run_id,
            **desired_fields(d),
        )

    # ---- entry point --------------------------------------------------------------------
    def execute(self, plan: Plan) -> ExecResult:
        try:
            if not self.dry_run:
                self._apply_records(plan)
            self._check_remote(plan)
            for d in plan.deletes:
                self._delete(d)
            for u in plan.updates:
                self._update(u)
            for c in plan.creates:
                self._create(c)
        except RunAborted as e:
            self.res.aborted = e
        return self.res

    # ---- DB-only changes ----------------------------------------------------------------
    def _apply_records(self, plan: Plan) -> None:
        with self.repo.tx():
            for occ_id, d in plan.refresh:
                self.repo.update_occurrence(
                    occ_id, last_seen_run_id=self.run_id, **_refresh_fields(d)
                )
            for r in plan.records:
                if r.occurrence_id is None and r.desired is not None:
                    occ_id = self._ensure_row(None, r.desired, r.state)
                    self.repo.update_occurrence(occ_id, state_reason=r.reason)
                else:
                    assert r.occurrence_id is not None
                    occ_id = r.occurrence_id
                    values: dict[str, Any] = {"state": r.state, "state_reason": r.reason}
                    if r.desired is not None:
                        values.update(desired_fields(r.desired))
                        values["last_seen_run_id"] = self.run_id
                    if r.state in ("cancelled", "past", "skipped"):
                        values["deferred_reason"] = None
                    if r.action == "warn":
                        values = {"state_reason": r.reason}
                    self.repo.update_occurrence(occ_id, **values)
                if r.action in ("fail",):
                    self.res.failed += 1
                if r.action == "skip":
                    self.res.skipped += 1
                if r.action in ("fail", "conflict", "cancel", "skip", "warn"):
                    title = r.desired.title if r.desired else None
                    self._item(Item(r.action, "ok", r.reason, occ_id, title=title))

    # ---- manual-change detection (R6) -----------------------------------------------------
    def _check_remote(self, plan: Plan) -> None:
        if self.dry_run:
            return
        ids = [d.broadcast_id for d in plan.deletes] + [u.broadcast_id for u in plan.updates]
        if not ids:
            return
        remote = self._call(lambda: self.yt.get_broadcasts(ids), None)
        if remote is None:
            plan.deletes, plan.updates = [], []
            return
        keep_d, keep_u = [], []
        for d in plan.deletes:
            if self._still_ours(d.occurrence_id, d.broadcast_id, remote, deleting=True):
                keep_d.append(d)
        for u in plan.updates:
            if self._still_ours(u.occurrence_id, u.broadcast_id, remote, deleting=False):
                keep_u.append(u)
        plan.deletes, plan.updates = keep_d, keep_u

    def _still_ours(
        self, occ_id: int, broadcast_id: str, remote: dict[str, Broadcast], *, deleting: bool
    ) -> bool:
        b = self.repo.broadcast(broadcast_id)
        assert b is not None
        r = remote.get(broadcast_id)
        if r is None:
            with self.repo.tx():
                self.repo.update_broadcast(broadcast_id, deleted_at=to_iso(utcnow()))
                if deleting:
                    self.repo.update_occurrence(occ_id, state="cancelled", state_reason=None)
                else:
                    self.repo.update_occurrence(
                        occ_id,
                        state="owner_deleted",
                        state_reason="deleted on YouTube by hand; it will not be recreated",
                    )
            self._item(
                Item(
                    "mark_owner_deleted" if not deleting else "delete",
                    "ok",
                    "already deleted on YouTube",
                    occ_id,
                    broadcast_id,
                )
            )
            return False
        self.repo.update_broadcast(
            broadcast_id,
            last_seen_remote_hash=r.managed_hash(),
            life_cycle_status=r.life_cycle_status,
        )
        if r.life_cycle_status not in MANAGEABLE_LIFECYCLE:
            self.repo.update_occurrence(occ_id, state="past", state_reason="already live or done")
            return False
        if b.last_written_hash != RECLAIMED and r.managed_hash() != b.last_written_hash:
            self.repo.update_occurrence(
                occ_id,
                state="owner_modified",
                state_reason="edited on YouTube by hand; the app will not overwrite it "
                "(use `occurrence reclaim` to hand it back)",
            )
            self._item(
                Item(
                    "mark_owner_modified",
                    "ok",
                    "edited on YouTube by hand; not overwritten",
                    occ_id,
                    broadcast_id,
                    title=r.title,
                )
            )
            return False
        return True

    # ---- API calls with error mapping (R8) ------------------------------------------------
    def _call(self, fn: Any, occ: Occurrence | int | None) -> Any:
        try:
            return fn()
        except AuthError as e:
            if not self.dry_run:
                self.repo.set_connection_status("needs_reauth", "YouTube access expired or revoked")
            raise RunAborted(
                "auth", "YouTube access expired or was revoked; run `connect` again"
            ) from e
        except NotEligibleError as e:
            if not self.dry_run:
                self.repo.set_connection_status(
                    "not_eligible", "the channel is not enabled for live streaming"
                )
            raise RunAborted(
                "not_eligible",
                "The channel is not enabled for live streaming (YouTube Studio → Go live)",
            ) from e

    def _defer(self, occ_id: int, reason: str, item: Item) -> None:
        if not self.dry_run:
            occ = self.repo.occurrence(occ_id)
            attempts = (occ.attempts if occ else 0) + 1
            self.repo.update_occurrence(occ_id, deferred_reason=reason, attempts=attempts)
        item.result = "deferred"
        item.message = (
            "YouTube daily limit reached; will retry next run"
            if reason == "quota"
            else "YouTube temporarily unavailable; will retry next run"
        )
        self.res.deferred += 1
        self._item(item)

    def _write_allowed(self, occ_id: int, item: Item) -> bool:
        if self._stop_writes:
            self._defer(occ_id, "quota", item)
            return False
        return True

    # ---- deletes ------------------------------------------------------------------------
    def _delete(self, d: Delete) -> None:
        item = Item("delete", "ok", d.reason, d.occurrence_id, d.broadcast_id)
        occ = self.repo.occurrence(d.occurrence_id)
        if occ:
            item.title, item.start_utc = occ.title, _dt(occ.start_utc)
        if self.dry_run:
            self.res.removed += 1
            self._item(item)
            return
        if not self._write_allowed(d.occurrence_id, item):
            return
        try:
            self._call(lambda: self.yt.delete_broadcast(d.broadcast_id), d.occurrence_id)
        except BroadcastNotFoundError:
            pass  # already gone: same end state
        except QuotaExceededError:
            self._stop_writes = True
            self.res.quota_hit = True
            self._defer(d.occurrence_id, "quota", item)
            return
        except TransientError:
            self._defer(d.occurrence_id, "transient", item)
            return
        with self.repo.tx():
            self.repo.update_broadcast(d.broadcast_id, deleted_at=to_iso(utcnow()))
            self.repo.update_occurrence(
                d.occurrence_id, state=d.new_state, state_reason=d.reason, deferred_reason=None
            )
        if d.new_state == "skipped":
            self.res.skipped += 1
        else:
            self.res.removed += 1
        self._item(item)

    # ---- updates ------------------------------------------------------------------------
    def _update(self, u: Update) -> None:
        item = Item(
            "update",
            "ok",
            None,
            u.occurrence_id,
            u.broadcast_id,
            u.desired.title,
            u.desired.start_utc,
        )
        if self.dry_run:
            self.res.updated += 1
            self._item(item)
            return
        if not self._write_allowed(u.occurrence_id, item):
            return
        try:
            remote = self._call(
                lambda: self.yt.update_broadcast(u.broadcast_id, u.desired.spec()), u.occurrence_id
            )
        except BroadcastNotFoundError:
            with self.repo.tx():
                self.repo.update_broadcast(u.broadcast_id, deleted_at=to_iso(utcnow()))
                self.repo.update_occurrence(
                    u.occurrence_id,
                    state="owner_deleted",
                    state_reason="deleted on YouTube by hand; it will not be recreated",
                )
            item.action, item.message = "mark_owner_deleted", "deleted on YouTube by hand"
            self._item(item)
            return
        except QuotaExceededError:
            self._stop_writes = True
            self.res.quota_hit = True
            self._defer(u.occurrence_id, "quota", item)
            return
        except TransientError:
            self._defer(u.occurrence_id, "transient", item)
            return
        except InvalidRequestError as e:
            self._fail(u.occurrence_id, e, item, keep_state="scheduled")
            return
        with self.repo.tx():
            self.repo.update_broadcast(
                u.broadcast_id,
                last_written_hash=remote.managed_hash(),
                last_written_at=to_iso(utcnow()),
                life_cycle_status=remote.life_cycle_status,
            )
            self.repo.update_occurrence(
                u.occurrence_id,
                state="scheduled",
                state_reason=None,
                deferred_reason=None,
                last_seen_run_id=self.run_id,
                **desired_fields(u.desired),
            )
        self.res.updated += 1
        self._item(item)

    # ---- creates ------------------------------------------------------------------------
    def _create(self, c: Create) -> None:
        d = c.desired
        if self.dry_run:
            self.res.created += 1
            self._item(Item("create", "ok", None, c.occurrence_id, None, d.title, d.start_utc))
            return
        with self.repo.tx():
            occ_id = self._ensure_row(c.occurrence_id, d, "pending")
            self.repo.update_occurrence(occ_id, last_seen_run_id=self.run_id, **desired_fields(d))
        item = Item("create", "ok", None, occ_id, None, d.title, d.start_utc)
        if not self._write_allowed(occ_id, item):
            self.repo.update_occurrence(occ_id, state="pending")
            return
        # Intent first, so a crash between insert and commit is recoverable (R5).
        self.repo.update_occurrence(occ_id, state="creating", intent_at=to_iso(utcnow()))
        try:
            b = self._call(lambda: self.yt.insert_broadcast(d.spec()), occ_id)
        except QuotaExceededError:
            self._stop_writes = True
            self.res.quota_hit = True
            self.repo.update_occurrence(occ_id, state="pending", intent_at=None)
            self._defer(occ_id, "quota", item)
            return
        except TransientError:
            self.repo.update_occurrence(occ_id, state="pending", intent_at=None)
            self._defer(occ_id, "transient", item)
            return
        except InvalidRequestError as e:
            self.repo.update_occurrence(occ_id, intent_at=None)
            self._fail(occ_id, e, item, keep_state=None)
            return
        except RunAborted:
            self.repo.update_occurrence(occ_id, state="pending", intent_at=None)
            raise
        with self.repo.tx():
            self.repo.insert_broadcast(
                broadcast_id=b.id,
                occurrence_id=occ_id,
                channel_id=self.channel_id,
                created_at=to_iso(utcnow()),
                last_written_hash=b.managed_hash(),
                last_written_at=to_iso(utcnow()),
                life_cycle_status=b.life_cycle_status,
            )
            self.repo.update_occurrence(
                occ_id, state="scheduled", state_reason=None, deferred_reason=None, intent_at=None
            )
        item.broadcast_id = b.id
        self.res.created += 1
        self._item(item)
        if self.stream_id:
            try:
                self._call(lambda: self.yt.bind(b.id, self.stream_id or ""), occ_id)
                self.repo.update_broadcast(b.id, bound_stream_id=self.stream_id)
            except (QuotaExceededError, TransientError, InvalidRequestError) as e:
                log.warning("could not bind stream to %s: %s", b.id, e)

    def _fail(
        self, occ_id: int, e: InvalidRequestError, item: Item, *, keep_state: str | None
    ) -> None:
        reason = REASONS.get(e.reason, f"YouTube rejected the request: {e.message}")
        self.repo.update_occurrence(
            occ_id, state=keep_state or "failed", state_reason=reason, deferred_reason=None
        )
        item.result, item.message = "error", reason
        item.action = "fail"
        self.res.failed += 1
        self._item(item)


def _dt(value: str) -> datetime:
    from ..timeutil import from_iso

    return from_iso(value)


def _refresh_fields(d: DesiredOccurrence) -> dict[str, Any]:
    """Fields refreshed for occurrences the app does not write (unmanaged/external)."""
    f = desired_fields(d)
    f.pop("desired_hash")
    return f
