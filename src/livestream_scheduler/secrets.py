"""Secret references: config holds references, never values (constitution Principle III)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class SecretError(Exception):
    """A secret reference could not be resolved."""


class CredentialRef(BaseModel):
    """Read from $CREDENTIALS_DIRECTORY/<name> (systemd LoadCredential=)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    credential: str


class EnvRef(BaseModel):
    """Read from an environment variable (development)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    env: str


class FileRef(BaseModel):
    """Read from a file that must be mode 0600 or 0400."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    file: str


SecretValue = CredentialRef | EnvRef | FileRef | str


def is_plain(value: SecretValue) -> bool:
    return isinstance(value, str)


def describe(value: SecretValue) -> str:
    """A loggable description of where a secret comes from (never the value)."""
    if isinstance(value, CredentialRef):
        return f"credential:{value.credential}"
    if isinstance(value, EnvRef):
        return f"env:{value.env}"
    if isinstance(value, FileRef):
        return f"file:{value.file}"
    return "plain string"


def resolve(value: SecretValue) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, CredentialRef):
        directory = os.environ.get("CREDENTIALS_DIRECTORY")
        path = Path(directory) / value.credential if directory else None
        if path is None or not path.is_file():
            raise SecretError(
                f'credential "{value.credential}" not found in $CREDENTIALS_DIRECTORY '
                "(is LoadCredential= set?)"
            )
        return _read(path)
    if isinstance(value, EnvRef):
        env = os.environ.get(value.env)
        if env is None:
            raise SecretError(f"env var {value.env} is not set")
        return env
    path = Path(value.file).expanduser()
    if not path.is_file():
        raise SecretError(f"secret file {path} not found")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise SecretError(f"secret file {path} has mode {mode:04o}, wider than 0600")
    return _read(path)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()
