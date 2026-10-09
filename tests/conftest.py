"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """An isolated, private state directory; systemd/env path variables are cleared."""
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    for var in (
        "LSS_CONFIG",
        "LSS_STATE_DIR",
        "STATE_DIRECTORY",
        "CONFIGURATION_DIRECTORY",
        "CREDENTIALS_DIRECTORY",
        "INVOCATION_ID",
        "JOURNAL_STREAM",
    ):
        monkeypatch.delenv(var, raising=False)
    yield state
