"""Typed accessors for the SQLite state (data-model.md). Writes happen inside `tx()`."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, fields
from typing import Any

from ..timeutil import to_iso, utcnow

ACTIVE_STATES = ("pending", "creating", "scheduled", "conflict", "failed", "exists_external")


@dataclass
class Connection:
    channel_id: str
    channel_title: str
    channel_handle: str
    status: str
    status_reason: str | None
    connected_at: str
    last_verified_at: str | None


@dataclass
class CalendarSource:
    url_hash: str | None
    etag: str | None
    last_modified: str | None
    last_fetched_at: str | None
    last_body_sha256: str | None
    last_event_count: int | None


@dataclass
class Occurrence:
    id: int
    key: str
    ical_uid: str
    original_start_utc: str | None
    title: str
    description: str
    start_utc: str
    end_utc: str
    source_tz: str
    visibility: str
    desired_hash: str
    state: str
    state_reason: str | None
    deferred_reason: str | None
    attempts: int
    intent_at: str | None
    local_override: str | None
    first_seen_run_id: int | None
    last_seen_run_id: int | None
    updated_at: str
    external_broadcast_id: str | None
    external_title: str | None
    external_start_utc: str | None


@dataclass
class Broadcast:
    broadcast_id: str
    occurrence_id: int | None
    channel_id: str
    created_at: str
    last_written_hash: str
    last_written_at: str
    last_seen_remote_hash: str | None
    life_cycle_status: str | None
    bound_stream_id: str | None
    deleted_at: str | None


@dataclass
class Run:
    id: int
    started_at: str
    finished_at: str | None
    trigger: str
    outcome: str | None
    dry_run: int
    created: int
    updated: int
    removed: int
    skipped: int
    deferred: int
    failed: int
    error_class: str | None
    error_message: str | None
    quota_units_est: int
    config_commit: str | None


@dataclass
class RunItem:
    id: int
    run_id: int
    occurrence_id: int | None
    action: str
    broadcast_id: str | None
    result: str
    message: str | None


@dataclass
class Notification:
    problem_key: str
    opened_at: str
    last_sent_at: str | None
    resolved_at: str | None
    summary: str | None


def _row[T](cls: type[T], row: sqlite3.Row | None) -> T | None:
    if row is None:
        return None
    names = {f.name for f in fields(cls)}  # type: ignore[arg-type]
    # sqlite3.Row iterates values, so .keys() is required here.
    return cls(**{k: row[k] for k in row.keys() if k in names})  # noqa: SIM118


def _rows[T](cls: type[T], rows: list[sqlite3.Row]) -> list[T]:
    return [r for r in (_row(cls, x) for x in rows) if r is not None]


class Repo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    @contextmanager
    def tx(self) -> Iterator[None]:
        if self.conn.in_transaction:
            yield
            return
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    def _update(self, table: str, where: str, key: Any, values: dict[str, Any]) -> None:
        if not values:
            return
        cols = ", ".join(f"{k} = ?" for k in values)
        self.conn.execute(f"UPDATE {table} SET {cols} WHERE {where} = ?", (*values.values(), key))

    # ---- channel_connection -------------------------------------------------------------
    def get_connection(self) -> Connection | None:
        return _row(Connection, self.conn.execute("SELECT * FROM channel_connection").fetchone())

    def save_connection(self, channel_id: str, title: str, handle: str) -> None:
        now = to_iso(utcnow())
        self.conn.execute(
            """INSERT INTO channel_connection
               (id, channel_id, channel_title, channel_handle, status, connected_at,
                last_verified_at)
               VALUES (1, ?, ?, ?, 'connected', ?, ?)
               ON CONFLICT(id) DO UPDATE SET channel_id=excluded.channel_id,
                 channel_title=excluded.channel_title, channel_handle=excluded.channel_handle,
                 status='connected', status_reason=NULL, connected_at=excluded.connected_at,
                 last_verified_at=excluded.last_verified_at""",
            (channel_id, title, handle, now, now),
        )

    def set_connection_status(self, status: str, reason: str | None = None) -> None:
        self.conn.execute(
            "UPDATE channel_connection SET status = ?, status_reason = ? WHERE id = 1",
            (status, reason),
        )

    def touch_verified(self) -> None:
        self.conn.execute(
            "UPDATE channel_connection SET last_verified_at = ?, status = 'connected', "
            "status_reason = NULL WHERE id = 1",
            (to_iso(utcnow()),),
        )

    def delete_connection(self) -> None:
        self.conn.execute("DELETE FROM channel_connection")

    # ---- calendar_source ----------------------------------------------------------------
    def get_calendar_source(self) -> CalendarSource | None:
        return _row(CalendarSource, self.conn.execute("SELECT * FROM calendar_source").fetchone())

    def save_calendar_source(self, **values: Any) -> None:
        self.conn.execute("INSERT OR IGNORE INTO calendar_source (id) VALUES (1)")
        self._update("calendar_source", "id", 1, values)

    # ---- occurrence ---------------------------------------------------------------------
    def occurrences(self, states: tuple[str, ...] | None = None) -> list[Occurrence]:
        if states:
            marks = ",".join("?" * len(states))
            rows = self.conn.execute(
                f"SELECT * FROM occurrence WHERE state IN ({marks}) ORDER BY start_utc, id", states
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM occurrence ORDER BY start_utc, id").fetchall()
        return _rows(Occurrence, rows)

    def occurrence(self, occurrence_id: int) -> Occurrence | None:
        return _row(
            Occurrence,
            self.conn.execute("SELECT * FROM occurrence WHERE id = ?", (occurrence_id,)).fetchone(),
        )

    def occurrence_by_key(self, key: str) -> Occurrence | None:
        return _row(
            Occurrence,
            self.conn.execute("SELECT * FROM occurrence WHERE key = ?", (key,)).fetchone(),
        )

    def insert_occurrence(self, **values: Any) -> int:
        values.setdefault("updated_at", to_iso(utcnow()))
        cols = ", ".join(values)
        marks = ", ".join("?" * len(values))
        cur = self.conn.execute(
            f"INSERT INTO occurrence ({cols}) VALUES ({marks})", tuple(values.values())
        )
        assert cur.lastrowid is not None
        return cur.lastrowid

    def update_occurrence(self, occurrence_id: int, **values: Any) -> None:
        values.setdefault("updated_at", to_iso(utcnow()))
        self._update("occurrence", "id", occurrence_id, values)

    # ---- broadcast ----------------------------------------------------------------------
    def owned_broadcast(self, occurrence_id: int) -> Broadcast | None:
        """The live (not deleted) broadcast this app created for an occurrence."""
        return _row(
            Broadcast,
            self.conn.execute(
                "SELECT * FROM broadcast WHERE occurrence_id = ? AND deleted_at IS NULL",
                (occurrence_id,),
            ).fetchone(),
        )

    def broadcast(self, broadcast_id: str) -> Broadcast | None:
        return _row(
            Broadcast,
            self.conn.execute(
                "SELECT * FROM broadcast WHERE broadcast_id = ?", (broadcast_id,)
            ).fetchone(),
        )

    def owned_broadcast_ids(self) -> set[str]:
        """Every id this app ever created (deleted or not): the ownership proof (research R5)."""
        return {r[0] for r in self.conn.execute("SELECT broadcast_id FROM broadcast")}

    def insert_broadcast(self, **values: Any) -> None:
        # The occurrence_id is unique; detach any earlier (deleted) broadcast row first.
        self.conn.execute(
            "UPDATE broadcast SET occurrence_id = NULL WHERE occurrence_id = ? "
            "AND deleted_at IS NOT NULL",
            (values["occurrence_id"],),
        )
        cols = ", ".join(values)
        marks = ", ".join("?" * len(values))
        self.conn.execute(
            f"INSERT INTO broadcast ({cols}) VALUES ({marks})", tuple(values.values())
        )

    def update_broadcast(self, broadcast_id: str, **values: Any) -> None:
        self._update("broadcast", "broadcast_id", broadcast_id, values)

    # ---- run / run_item -----------------------------------------------------------------
    def start_run(self, trigger: str, dry_run: bool, config_commit: str | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO run (started_at, trigger, dry_run, config_commit) VALUES (?, ?, ?, ?)",
            (to_iso(utcnow()), trigger, int(dry_run), config_commit),
        )
        assert cur.lastrowid is not None
        return cur.lastrowid

    def finish_run(self, run_id: int, **values: Any) -> None:
        values.setdefault("finished_at", to_iso(utcnow()))
        self._update("run", "id", run_id, values)

    def add_item(
        self,
        run_id: int,
        action: str,
        result: str = "ok",
        message: str | None = None,
        occurrence_id: int | None = None,
        broadcast_id: str | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO run_item (run_id, occurrence_id, action, broadcast_id, result, message) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, occurrence_id, action, broadcast_id, result, message),
        )

    def runs(self, limit: int = 10) -> list[Run]:
        return _rows(
            Run,
            self.conn.execute("SELECT * FROM run ORDER BY id DESC LIMIT ?", (limit,)).fetchall(),
        )

    def run(self, run_id: int) -> Run | None:
        return _row(Run, self.conn.execute("SELECT * FROM run WHERE id = ?", (run_id,)).fetchone())

    def last_run(self, include_dry_run: bool = False) -> Run | None:
        sql = (
            "SELECT * FROM run WHERE outcome IS NOT NULL AND outcome != 'skipped_locked' "
            "AND NOT EXISTS (SELECT 1 FROM run_item i WHERE i.run_id = run.id "
            "AND i.action = 'backup')"
        )
        if not include_dry_run:
            sql += " AND dry_run = 0"
        return _row(Run, self.conn.execute(sql + " ORDER BY id DESC LIMIT 1").fetchone())

    def items(self, run_id: int) -> list[RunItem]:
        return _rows(
            RunItem,
            self.conn.execute(
                "SELECT * FROM run_item WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall(),
        )

    # ---- notification -------------------------------------------------------------------
    def notification(self, key: str) -> Notification | None:
        return _row(
            Notification,
            self.conn.execute(
                "SELECT * FROM notification WHERE problem_key = ?", (key,)
            ).fetchone(),
        )

    def open_problems(self) -> list[Notification]:
        return _rows(
            Notification,
            self.conn.execute(
                "SELECT * FROM notification WHERE resolved_at IS NULL ORDER BY opened_at"
            ).fetchall(),
        )

    def upsert_notification(self, key: str, **values: Any) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO notification (problem_key, opened_at) VALUES (?, ?)",
            (key, to_iso(utcnow())),
        )
        self._update("notification", "problem_key", key, values)

    def reopen_notification(self, key: str, summary: str) -> None:
        self.conn.execute(
            "UPDATE notification SET opened_at = ?, last_sent_at = NULL, resolved_at = NULL, "
            "summary = ? WHERE problem_key = ?",
            (to_iso(utcnow()), summary, key),
        )
