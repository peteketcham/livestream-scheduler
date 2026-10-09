"""001 User Story 4 — back up, restore, move the installation (FR-018..FR-022)."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tarfile
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from livestream_scheduler import backup as backup_mod
from livestream_scheduler.db.migrate import latest_version
from tests.harness import Env

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)
SECRETS = ("ya29.", "refresh_token", "fake-refresh", "GOCSPX-", "fake-secret")


def _backup(env: Env, **kw: object) -> Path:
    out = env.root / "backups"
    return backup_mod.backup(
        env.config(),
        env.state,
        env.config_path.parent,
        out,
        **kw,  # type: ignore[arg-type]
    )


def _members(path: Path) -> list[str]:
    with tarfile.open(path) as tar:
        return sorted(m.name for m in tar.getmembers() if m.isfile())


def test_default_backup_contents_and_no_secrets(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.sync(NOW)
    path = _backup(env)
    assert path.name.startswith("lss-backup-") and path.name.endswith(".tar.gz")
    assert path.stat().st_mode & 0o077 == 0
    names = _members(path)
    assert "manifest.json" in names and "state.db" in names
    assert "config/config.yaml" in names and "config/calendar.ics" in names
    assert not any("token" in n or "credentials" in n for n in names)
    with tarfile.open(path) as tar:
        manifest = json.load(tar.extractfile("manifest.json"))  # type: ignore[arg-type]
        blob = b"".join(
            tar.extractfile(m).read()  # type: ignore[union-attr]
            for m in tar.getmembers()
            if m.isfile() and m.name != "state.db"
        )
    assert manifest["secrets_included"] is False
    assert manifest["schema_version"] == latest_version()
    assert manifest["channel_id"] == "UCzwZQ34D3RZEncTf6fAe0hQ"
    assert {f["path"] for f in manifest["files"]} >= {"state.db", "config/config.yaml"}
    for s in SECRETS:
        assert s.encode() not in blob


def test_snapshot_is_consistent_while_another_connection_writes(env: Env) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.sync(NOW)
    stop = threading.Event()

    def writer() -> None:
        conn = sqlite3.connect(env.state / "state.db", timeout=30)
        while not stop.is_set():
            conn.execute("UPDATE occurrence SET attempts = attempts + 1")
            conn.commit()
        conn.close()

    t = threading.Thread(target=writer)
    t.start()
    try:
        path = _backup(env)
    finally:
        stop.set()
        t.join()
    extract = env.root / "x"
    with tarfile.open(path) as tar:
        tar.extract("state.db", extract, filter="data")
    conn = sqlite3.connect(extract / "state.db")
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("SELECT COUNT(*) FROM occurrence").fetchone()[0] == 4


def test_prune_keeps_newest(env: Env) -> None:
    env.connect_offline()
    env.write_config(backup={"dir": str(env.root / "backups"), "keep": 2})
    paths = []
    for n in range(4):
        import time_machine

        with time_machine.travel(NOW + n * HOUR, tick=False):
            paths.append(_backup(env, prune_keep=2))
    remaining = sorted(p.name for p in (env.root / "backups").iterdir())
    assert remaining == sorted(p.name for p in paths[-2:])


def test_include_secrets_requires_age(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    env.connect_offline()
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(backup_mod.BackupError, match="age"):
        _backup(env, include_secrets=True)


def test_restore_on_fresh_server_keeps_managing(env: Env, tmp_path: Path) -> None:
    env.use_calendar("weekly.ics")
    env.connect_offline()
    env.sync(NOW)
    ids_before = sorted(env.yt.broadcasts)
    path = _backup(env)

    # "new server": empty state dir, same config repo, same channel
    new = Env(root=tmp_path / "new", yt=env.yt)
    new.write_config()
    shutil.copyfile(env.calendar, new.calendar)
    report = backup_mod.restore(path, new.config(), new.state, new.config_path.parent)
    assert report.needs_connect  # default backups carry no token
    new.connect_offline()
    sync = new.sync(NOW + HOUR, dry_run=True)
    assert sync.counts["created"] == 0
    cal = new.calendar.read_text().replace("SUMMARY:Weekly Q&A", "SUMMARY:Weekly Q and A")
    new.write_calendar(cal)
    real = new.sync(NOW + 2 * HOUR)
    assert real.counts["updated"] == 4 and real.counts["created"] == 0
    assert sorted(env.yt.broadcasts) == ids_before  # same videos, now renamed
    assert (new.state / "state.db").stat().st_mode & 0o077 == 0


def test_restore_refusals_write_nothing(env: Env, tmp_path: Path) -> None:
    import time_machine

    env.use_calendar("weekly.ics")
    env.connect_offline()
    with time_machine.travel(NOW, tick=False):
        path = _backup(env)
    target = tmp_path / "t"
    target.mkdir(mode=0o700)

    # newer schema
    bumped = _rewrite_manifest(path, tmp_path, schema_version=latest_version() + 1)
    with pytest.raises(backup_mod.BackupError, match="newer"):
        backup_mod.restore(bumped, env.config(), target, env.config_path.parent)
    # newer app version
    newer_app = _rewrite_manifest(path, tmp_path, app_version="99.0.0")
    with pytest.raises(backup_mod.BackupError, match="newer"):
        backup_mod.restore(newer_app, env.config(), target, env.config_path.parent)
    # channel mismatch
    other = _rewrite_manifest(path, tmp_path, channel_id="UCother", channel_handle="@other")
    with pytest.raises(backup_mod.BackupError, match="channel"):
        backup_mod.restore(other, env.config(), target, env.config_path.parent)
    assert list(target.iterdir()) == []

    # existing newer state without --force
    env.sync(NOW + HOUR)
    with pytest.raises(backup_mod.BackupError, match="--force"):
        backup_mod.restore(path, env.config(), env.state, env.config_path.parent)
    backup_mod.restore(path, env.config(), env.state, env.config_path.parent, force=True)


def test_tampered_backup_is_refused(env: Env, tmp_path: Path) -> None:
    env.connect_offline()
    path = _backup(env)
    tampered = _rewrite_manifest(path, tmp_path, corrupt="state.db")
    with pytest.raises(backup_mod.BackupError, match="checksum"):
        backup_mod.restore(tampered, env.config(), tmp_path / "t2", env.config_path.parent)


@pytest.mark.skipif(shutil.which("age") is None, reason="age not installed")
def test_encrypted_backup_needs_a_terminal(env: Env) -> None:  # pragma: no cover - needs age
    # age reads passphrases only from a TTY; covered by the manual quickstart scenario 16.
    env.connect_offline()
    with pytest.raises(backup_mod.BackupError, match="terminal"):
        _backup(env, include_secrets=True, interactive=False)


def _rewrite_manifest(path: Path, tmp: Path, corrupt: str | None = None, **changes: object) -> Path:
    work = tmp / f"rw-{len(list(tmp.iterdir()))}"
    work.mkdir()
    with tarfile.open(path) as tar:
        tar.extractall(work, filter="data")
    manifest = json.loads((work / "manifest.json").read_text())
    manifest.update(changes)
    (work / "manifest.json").write_text(json.dumps(manifest))
    if corrupt:
        (work / corrupt).write_bytes(b"tampered")
    out = tmp / f"{work.name}.tar.gz"
    with tarfile.open(out, "w:gz") as tar:
        for p in sorted(work.rglob("*")):
            tar.add(p, arcname=str(p.relative_to(work)), recursive=False)
    return out
