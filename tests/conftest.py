"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.harness import Env

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


@pytest.fixture
def env(tmp_path: Path, tmp_state_dir: Path) -> Iterator[Env]:
    from livestream_scheduler import cli as cli_mod

    e = Env(root=tmp_path)
    e.write_config()
    saved = (cli_mod.YOUTUBE_FACTORY, cli_mod.CONSENT, cli_mod.AFTER_RUN)
    yield e
    cli_mod.YOUTUBE_FACTORY, cli_mod.CONSENT, cli_mod.AFTER_RUN = saved
