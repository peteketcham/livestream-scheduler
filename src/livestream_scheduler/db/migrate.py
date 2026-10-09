"""Forward-only SQL migrations from db/schema/NNNN_*.sql (research R12)."""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

SCHEMA_PACKAGE = "livestream_scheduler.db.schema"


def _migrations() -> list[tuple[int, str, str]]:
    found = []
    for entry in resources.files(SCHEMA_PACKAGE).iterdir():
        name = entry.name
        if name.endswith(".sql") and name[:4].isdigit():
            found.append((int(name[:4]), name, entry.read_text(encoding="utf-8")))
    return sorted(found)


def latest_version() -> int:
    migs = _migrations()
    return migs[-1][0] if migs else 0


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, isolation_level=None, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def current_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return int(row[0] or 0)


def migrate(conn: sqlite3.Connection) -> int:
    """Apply pending migrations; returns the resulting schema version."""
    version = current_version(conn)
    for number, _name, sql in _migrations():
        if number <= version:
            continue
        script = (
            "BEGIN IMMEDIATE;\n"
            + sql
            + f"\n;INSERT INTO schema_version(version) VALUES ({number});\nCOMMIT;"
        )
        try:
            conn.executescript(script)
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        version = number
    return version


def open_db(state_dir: Path) -> sqlite3.Connection:
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    conn = connect(state_dir / "state.db")
    migrate(conn)
    return conn
