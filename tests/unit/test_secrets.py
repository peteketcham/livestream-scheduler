from __future__ import annotations

import os
from pathlib import Path

import pytest

from livestream_scheduler.secrets import (
    CredentialRef,
    EnvRef,
    FileRef,
    SecretError,
    is_plain,
    resolve,
)


def test_credential_ref_reads_credentials_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "calendar-url").write_text("https://example.org/ical/secret/basic.ics\n")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    assert (
        resolve(CredentialRef(credential="calendar-url"))
        == "https://example.org/ical/secret/basic.ics"
    )


def test_missing_credential_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    with pytest.raises(SecretError) as e:
        resolve(CredentialRef(credential="calendar-url"))
    assert str(e.value) == (
        'credential "calendar-url" not found in $CREDENTIALS_DIRECTORY (is LoadCredential= set?)'
    )


def test_credential_without_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    with pytest.raises(SecretError, match="LoadCredential"):
        resolve(CredentialRef(credential="smtp-password"))


def test_env_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LSS_SMTP_PASSWORD", "hunter2")
    assert resolve(EnvRef(env="LSS_SMTP_PASSWORD")) == "hunter2"
    monkeypatch.delenv("LSS_SMTP_PASSWORD")
    with pytest.raises(SecretError, match="env var LSS_SMTP_PASSWORD is not set"):
        resolve(EnvRef(env="LSS_SMTP_PASSWORD"))


@pytest.mark.parametrize("mode", [0o600, 0o400])
def test_file_ref_accepts_private_modes(tmp_path: Path, mode: int) -> None:
    f = tmp_path / "secret"
    f.write_text("s3cret\n")
    os.chmod(f, mode)
    assert resolve(FileRef(file=str(f))) == "s3cret"


def test_file_ref_rejects_wide_modes(tmp_path: Path) -> None:
    f = tmp_path / "secret"
    f.write_text("s3cret")
    os.chmod(f, 0o644)
    with pytest.raises(SecretError, match="wider than 0600"):
        resolve(FileRef(file=str(f)))


def test_plain_string_resolves_and_is_flagged() -> None:
    assert resolve("literal") == "literal"
    assert is_plain("literal")
    assert not is_plain(EnvRef(env="X"))
