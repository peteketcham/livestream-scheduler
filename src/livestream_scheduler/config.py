"""YAML configuration (contracts/config-schema.md). Unknown keys are errors."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .secrets import CredentialRef, SecretValue, is_plain

Visibility = Literal["public", "unlisted", "private"]


class ConfigError(Exception):
    """Configuration could not be loaded or validated (exit code 2)."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoogleConfig(_Model):
    client_secret: SecretValue = CredentialRef(credential="oauth-client")


class IncludeFilter(_Model):
    summary_prefix: str | None = None
    directive: bool = False


class CalendarConfig(_Model):
    url: SecretValue | None = None
    path: str | None = None
    include: IncludeFilter = IncludeFilter()

    @model_validator(mode="after")
    def _one_source(self) -> CalendarConfig:
        if (self.url is None) == (self.path is None):
            raise ValueError("calendar: set exactly one of url, path")
        if isinstance(self.url, str) and not self.url.startswith("https://"):
            raise ValueError("calendar.url must be https://")
        return self


class DefaultsConfig(_Model):
    timezone: str = "America/Chicago"
    visibility: Visibility = "public"
    made_for_kids: bool = False
    enable_auto_start: bool = False
    enable_auto_stop: bool = False
    enable_dvr: bool = True

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f'defaults.timezone: unknown time zone "{v}"') from None
        return v


class YouTubeConfig(_Model):
    channel_handle: str
    channel_id: str | None = None
    stream_id: str | None = None

    @field_validator("channel_handle")
    @classmethod
    def _handle(cls, v: str) -> str:
        if not v.startswith("@") or len(v) < 2:
            raise ValueError("youtube.channel_handle: must look like @handle")
        return v


class HorizonConfig(_Model):
    days: int = Field(28, ge=1, le=180)


class SafetyConfig(_Model):
    min_lead_minutes: int = Field(15, ge=0)
    max_removals_per_run: int = Field(5, ge=0)


class NotifyConfig(_Model):
    email_to: str
    email_from: str
    smtp_host: str
    smtp_port: int = 587
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_user: str | None = None
    smtp_password: SecretValue | None = None
    reminder_hours: int = Field(24, ge=1)


class BackupConfig(_Model):
    dir: str = "/var/backups/livestream-scheduler"
    keep: int = Field(14, ge=1)
    passphrase: SecretValue | None = None

    @field_validator("dir")
    @classmethod
    def _abs(cls, v: str) -> str:
        if not v.startswith("/"):
            raise ValueError("backup.dir must be an absolute path")
        return v


class Config(_Model):
    version: Literal[1] = 1
    google: GoogleConfig = GoogleConfig()
    calendar: CalendarConfig
    defaults: DefaultsConfig = DefaultsConfig()
    youtube: YouTubeConfig
    horizon: HorizonConfig = HorizonConfig()
    overlaps: Literal["warn", "allow"] = "warn"
    safety: SafetyConfig = SafetyConfig()
    notify: NotifyConfig
    retention_days: int = Field(90, ge=1)
    backup: BackupConfig = BackupConfig()


def _format_errors(err: ValidationError) -> str:
    lines = []
    for e in err.errors():
        loc = ".".join(str(p) for p in e["loc"] if not str(p).startswith("function-"))
        msg = str(e["msg"]).removeprefix("Value error, ")
        if e["type"] == "extra_forbidden":
            msg = f"unknown key {loc!r} (typo?)"
        elif e["type"] in ("greater_than_equal", "less_than_equal") or (
            loc and not msg.startswith(loc.split(".")[0])
        ):
            msg = f"{loc}: {msg}"
        lines.append(msg)
    return "; ".join(dict.fromkeys(lines))


def parse_config(data: dict[str, Any]) -> tuple[Config, list[str]]:
    try:
        cfg = Config.model_validate(data)
    except ValidationError as e:
        raise ConfigError(_format_errors(e)) from None
    warnings: list[str] = []
    if cfg.calendar.url is not None and is_plain(cfg.calendar.url):
        warnings.append(
            "calendar.url is a plain string; it is a secret — use {credential: calendar-url}"
        )
    if cfg.notify.smtp_password is not None and is_plain(cfg.notify.smtp_password):
        warnings.append("notify.smtp_password is a plain string; use a credential reference")
    return cfg, warnings


def load_config(path: Path) -> tuple[Config, list[str]]:
    if not path.is_file():
        raise ConfigError(f"config file {path} not found")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"{path}: invalid YAML: {e}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return parse_config(data)
