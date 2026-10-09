"""Backup and restore (research R18; FR-019..FR-021).

Default backups contain the state DB snapshot and the active config — never secrets.
`--include-secrets` adds the token and credentials and encrypts the whole archive with
`age -p`, which reads the passphrase from the terminal (age has no non-interactive
passphrase input, so encrypted backups are interactive by design).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from .config import Config
from .db.migrate import connect, current_version, latest_version, migrate, open_db
from .db.repo import Repo
from .lock import LockHeldError, run_lock
from .timeutil import to_iso, utcnow

PREFIX = "lss-backup-"
LOCK_WAIT_SECONDS = 600


class BackupError(Exception):
    """Backup/restore refused or failed (exit code 2)."""


@dataclass
class RestoreReport:
    restored_files: list[str] = field(default_factory=list)
    needs_connect: bool = True
    credentials_dir: Path | None = None
    credentials: list[str] = field(default_factory=list)
    config_commit: str | None = None
    applied_config: bool = False


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split(".") if p.isdigit())


def _wait_lock(state_dir: Path) -> Any:
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            cm = run_lock(state_dir)
            cm.__enter__()
            return cm
        except LockHeldError:
            if time.monotonic() > deadline:
                raise BackupError(
                    "a sync run has held the lock for 10 minutes; try later"
                ) from None
            time.sleep(2)


def _config_commit(config_dir: Path) -> str | None:
    head = config_dir / ".git" / "HEAD"
    try:
        ref = head.read_text().strip()
        if ref.startswith("ref: "):
            ref = (config_dir / ".git" / ref[5:]).read_text().strip()
        return ref[:12]
    except OSError:
        return None


def _age() -> str:
    exe = shutil.which("age")
    if exe is None:
        raise BackupError(
            "--include-secrets needs the `age` tool "
            "(Ubuntu: apt install age; macOS: brew install age)"
        )
    return exe


def backup(
    cfg: Config,
    state_dir: Path,
    config_dir: Path,
    output_dir: Path,
    *,
    include_secrets: bool = False,
    prune_keep: int | None = None,
    interactive: bool | None = None,
) -> Path:
    if include_secrets:
        age = _age()
        if cfg.backup.passphrase is not None:
            raise BackupError(
                "backup.passphrase is not supported: age reads passphrases only from a terminal"
            )
        if not (interactive if interactive is not None else sys.stdin.isatty()):
            raise BackupError(
                "--include-secrets must be run from a terminal (age asks for a passphrase)"
            )
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = utcnow().strftime("%Y%m%dT%H%M%SZ")
    name = f"{PREFIX}{stamp}-v{__version__}.tar.gz"

    lock = _wait_lock(state_dir)
    try:
        with tempfile.TemporaryDirectory(prefix="lss-backup-") as tmp_s:
            tmp = Path(tmp_s)
            os.chmod(tmp, 0o700)
            # Consistent snapshot via SQLite's online backup API (safe during writes).
            src = open_db(state_dir)
            schema = current_version(src)
            conn_row = Repo(src).get_connection()
            dst = sqlite3.connect(tmp / "state.db")
            src.backup(dst)
            dst.close()
            src.close()

            cfg_out = tmp / "config"
            shutil.copytree(config_dir, cfg_out, ignore=shutil.ignore_patterns(".git"))
            if include_secrets:
                secrets = tmp / "secrets"
                secrets.mkdir(mode=0o700)
                token = state_dir / "token.json"
                if token.is_file():
                    shutil.copy2(token, secrets / "token.json")
                cred_dir = os.environ.get("CREDENTIALS_DIRECTORY")
                if cred_dir:
                    shutil.copytree(cred_dir, secrets / "credentials")

            files = sorted(p for p in tmp.rglob("*") if p.is_file())
            manifest = {
                "app_version": __version__,
                "schema_version": schema,
                "created_at": to_iso(utcnow()),
                "channel_id": conn_row.channel_id if conn_row else cfg.youtube.channel_id,
                "channel_handle": conn_row.channel_handle
                if conn_row
                else cfg.youtube.channel_handle,
                "config_commit": _config_commit(config_dir),
                "secrets_included": include_secrets,
                "files": [{"path": str(p.relative_to(tmp)), "sha256": _sha256(p)} for p in files],
            }
            (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2))

            archive = output_dir / name
            fd = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as raw, tarfile.open(fileobj=raw, mode="w:gz") as tar:
                for p in [tmp / "manifest.json", *files]:
                    tar.add(p, arcname=str(p.relative_to(tmp)), recursive=False)
            if include_secrets:
                encrypted = archive.with_name(archive.name + ".age")
                result = subprocess.run(
                    [age, "-p", "-o", str(encrypted), str(archive)], check=False
                )
                archive.unlink()
                if result.returncode != 0:
                    encrypted.unlink(missing_ok=True)
                    raise BackupError("age encryption failed; no backup was written")
                os.chmod(encrypted, 0o600)
                archive = encrypted
    finally:
        lock.__exit__(None, None, None)

    if prune_keep is not None:
        prune(output_dir, prune_keep)
    return archive


def prune(output_dir: Path, keep: int) -> list[Path]:
    backups = sorted(p for p in output_dir.iterdir() if p.name.startswith(PREFIX))
    removed = backups[:-keep] if keep > 0 else backups
    for p in removed:
        p.unlink()
    return removed


def latest_backup(output_dir: Path) -> Path | None:
    try:
        backups = sorted(p for p in output_dir.iterdir() if p.name.startswith(PREFIX))
    except OSError:
        return None
    return backups[-1] if backups else None


def _extract(archive: Path, dest: Path) -> None:
    with tarfile.open(archive) as tar:
        tar.extractall(dest, filter="data")


def restore(
    archive: Path,
    cfg: Config,
    state_dir: Path,
    config_dir: Path,
    *,
    force: bool = False,
    apply_config: bool = False,
) -> RestoreReport:
    report = RestoreReport()
    with tempfile.TemporaryDirectory(prefix="lss-restore-") as tmp_s:
        tmp = Path(tmp_s)
        os.chmod(tmp, 0o700)
        plain = archive
        if archive.name.endswith(".age"):
            plain = tmp / "backup.tar.gz"
            result = subprocess.run([_age(), "-d", "-o", str(plain), str(archive)], check=False)
            if result.returncode != 0:
                raise BackupError(
                    "could not decrypt the backup (wrong passphrase?); nothing restored"
                )
        work = tmp / "x"
        work.mkdir()
        try:
            _extract(plain, work)
        except (tarfile.TarError, OSError) as e:
            raise BackupError(f"not a valid backup archive: {e}") from None
        manifest_path = work / "manifest.json"
        if not manifest_path.is_file():
            raise BackupError("not a livestream-scheduler backup (no manifest.json)")
        manifest = json.loads(manifest_path.read_text())

        for entry in manifest.get("files", []):
            p = work / entry["path"]
            if not p.is_file() or _sha256(p) != entry["sha256"]:
                raise BackupError(f"checksum mismatch for {entry['path']}; backup is damaged")
        if int(manifest["schema_version"]) > latest_version():
            raise BackupError(
                f"backup schema {manifest['schema_version']} is newer than this installation "
                f"({latest_version()}); upgrade the app first"
            )
        if _version_tuple(str(manifest["app_version"])) > _version_tuple(__version__):
            raise BackupError(
                f"backup was made by a newer app version ({manifest['app_version']} > "
                f"{__version__}); upgrade the app first"
            )
        want_id, want_handle = cfg.youtube.channel_id, cfg.youtube.channel_handle
        got_id, got_handle = manifest.get("channel_id"), manifest.get("channel_handle") or ""
        if (want_id and got_id and want_id != got_id) or (
            got_handle and got_handle.lstrip("@").casefold() != want_handle.lstrip("@").casefold()
        ):
            raise BackupError(
                f"backup is for channel {got_handle or got_id}, but this installation is "
                f"configured for {want_handle}"
            )

        existing = state_dir / "state.db"
        if existing.is_file() and not force:
            conn = connect(existing)
            try:
                row = conn.execute("SELECT MAX(started_at) FROM run").fetchone()
            except sqlite3.Error:
                row = (None,)
            finally:
                conn.close()
            if row and row[0] and row[0] > manifest["created_at"]:
                raise BackupError(
                    "this installation has runs newer than the backup; use --force to overwrite"
                )

        state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        with run_lock(state_dir):
            for suffix in ("", "-wal", "-shm"):
                (state_dir / f"state.db{suffix}").unlink(missing_ok=True)
            fd = os.open(existing, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as out:
                out.write((work / "state.db").read_bytes())
            report.restored_files.append("state.db")
            token = work / "secrets" / "token.json"
            if token.is_file():
                dest = state_dir / "token.json"
                fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "wb") as out:
                    out.write(token.read_bytes())
                report.restored_files.append("token.json")
                report.needs_connect = False
            creds = work / "secrets" / "credentials"
            if creds.is_dir():
                target = state_dir / "restored-credentials"
                shutil.rmtree(target, ignore_errors=True)
                shutil.copytree(creds, target)
                os.chmod(target, 0o700)
                for f in target.iterdir():
                    os.chmod(f, 0o600)
                    report.credentials.append(f.name)
                report.credentials_dir = target
            conn = connect(existing)
            migrate(conn)
            conn.close()
        report.config_commit = manifest.get("config_commit")
        if apply_config:
            for p in (work / "config").rglob("*"):
                if p.is_file():
                    dest = config_dir / p.relative_to(work / "config")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, dest)
            report.applied_config = True
    return report
