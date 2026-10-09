"""Where config and state live (contracts/deployment.md "How the app reads its environment")."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import platformdirs

APP_NAME = "livestream-scheduler"


class InsecurePermissionsError(Exception):
    """A private file is readable or writable by group/others."""


def _first(env_value: str) -> str:
    # systemd may pass several colon-separated directories; the first is ours.
    return env_value.split(":", 1)[0]


def config_path(cli: str | None) -> Path:
    """--config → $LSS_CONFIG → $CONFIGURATION_DIRECTORY/config.yaml → user config dir."""
    if cli:
        return Path(cli)
    if env := os.environ.get("LSS_CONFIG"):
        return Path(env)
    if env := os.environ.get("CONFIGURATION_DIRECTORY"):
        return Path(_first(env)) / "config.yaml"
    return Path(platformdirs.user_config_dir(APP_NAME)) / "config.yaml"


def state_dir(cli: str | None) -> Path:
    """--state-dir → $LSS_STATE_DIR → $STATE_DIRECTORY → user state dir."""
    if cli:
        return Path(cli)
    if env := os.environ.get("LSS_STATE_DIR"):
        return Path(env)
    if env := os.environ.get("STATE_DIRECTORY"):
        return Path(_first(env))
    return Path(platformdirs.user_state_dir(APP_NAME))


def ensure_private(path: Path) -> None:
    """Refuse files that group/others can access (0600 and 0400 are fine)."""
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise InsecurePermissionsError(
            f"{path} has mode {stat.S_IMODE(mode):04o}; it must be 0600 (or 0400). "
            f"Fix with: chmod 600 {path}"
        )


def ensure_state_dir(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path
