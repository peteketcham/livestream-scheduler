"""Single-run lock (research R13): a second `sync` exits 0 with "already running"."""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class LockHeldError(Exception):
    """Another run holds the lock."""


@contextmanager
def run_lock(state_dir: Path) -> Iterator[None]:
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(state_dir / "state.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LockHeldError("another livestream-scheduler run is in progress") from None
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
