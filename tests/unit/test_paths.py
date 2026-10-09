from __future__ import annotations

import os
from pathlib import Path

import pytest

from livestream_scheduler import paths


def test_config_path_precedence(tmp_state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIGURATION_DIRECTORY", "/etc/livestream-scheduler")
    assert paths.config_path(None) == Path("/etc/livestream-scheduler/config.yaml")
    monkeypatch.setenv("LSS_CONFIG", "/tmp/x.yaml")
    assert paths.config_path(None) == Path("/tmp/x.yaml")
    assert paths.config_path("/cli.yaml") == Path("/cli.yaml")


def test_config_path_falls_back_to_user_dir(tmp_state_dir: Path) -> None:
    p = paths.config_path(None)
    assert p.name == "config.yaml"
    assert "livestream-scheduler" in str(p)


def test_state_dir_precedence(tmp_state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STATE_DIRECTORY", "/var/lib/livestream-scheduler:/var/lib/other")
    assert paths.state_dir(None) == Path("/var/lib/livestream-scheduler")
    monkeypatch.setenv("LSS_STATE_DIR", str(tmp_state_dir))
    assert paths.state_dir(None) == tmp_state_dir
    assert paths.state_dir("/cli/state") == Path("/cli/state")


def test_state_dir_user_fallback(tmp_state_dir: Path) -> None:
    assert "livestream-scheduler" in str(paths.state_dir(None))


def test_ensure_private_accepts_0600_and_0400(tmp_path: Path) -> None:
    f = tmp_path / "token.json"
    f.write_text("{}")
    os.chmod(f, 0o600)
    paths.ensure_private(f)
    os.chmod(f, 0o400)
    paths.ensure_private(f)


def test_ensure_private_rejects_group_readable(tmp_path: Path) -> None:
    f = tmp_path / "token.json"
    f.write_text("{}")
    os.chmod(f, 0o640)
    with pytest.raises(paths.InsecurePermissionsError, match="0600"):
        paths.ensure_private(f)


def test_ensure_private_missing_file_is_ok(tmp_path: Path) -> None:
    paths.ensure_private(tmp_path / "absent.json")
