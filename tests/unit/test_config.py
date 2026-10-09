from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from livestream_scheduler.config import ConfigError, load_config

BASE: dict[str, Any] = {
    "version": 1,
    "google": {"client_secret": {"credential": "oauth-client"}},
    "calendar": {"url": {"credential": "calendar-url"}},
    "defaults": {"timezone": "America/Chicago", "visibility": "public"},
    "youtube": {"channel_handle": "@minnehahaumc"},
    "notify": {
        "email_to": "owner@example.org",
        "email_from": "scheduler@example.org",
        "smtp_host": "smtp.example.org",
        "smtp_user": "scheduler@example.org",
        "smtp_password": {"credential": "smtp-password"},
    },
}


def _write(tmp_path: Path, data: dict[str, Any]) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


def _with(**overrides: Any) -> dict[str, Any]:
    import copy

    d = copy.deepcopy(BASE)
    for dotted, value in overrides.items():
        cur = d
        parts = dotted.split("__")
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})
        if value is _DELETE:
            cur.pop(parts[-1], None)
        else:
            cur[parts[-1]] = value
    return d


_DELETE = object()


def test_valid_config_and_defaults(tmp_path: Path) -> None:
    cfg, warnings = load_config(_write(tmp_path, BASE))
    assert cfg.horizon.days == 28
    assert cfg.safety.min_lead_minutes == 15
    assert cfg.safety.max_removals_per_run == 5
    assert cfg.overlaps == "warn"
    assert cfg.retention_days == 90
    assert cfg.backup.keep == 14
    assert cfg.backup.dir == "/var/backups/livestream-scheduler"
    assert cfg.youtube.channel_handle == "@minnehahaumc"
    assert warnings == []


def test_exactly_one_of_url_or_path(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="calendar: set exactly one of url, path"):
        load_config(_write(tmp_path, _with(calendar__path="./x.ics")))
    with pytest.raises(ConfigError, match="calendar: set exactly one of url, path"):
        load_config(_write(tmp_path, _with(calendar__url=_DELETE)))


def test_unknown_keys_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="horizn"):
        load_config(_write(tmp_path, _with(horizn={"days": 3})))


def test_bad_timezone(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=re.escape('defaults.timezone: unknown time zone "EST5"')):
        load_config(_write(tmp_path, _with(defaults__timezone="EST5")))


def test_bad_visibility(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="visibility"):
        load_config(_write(tmp_path, _with(defaults__visibility="secret")))


@pytest.mark.parametrize("days", [0, 181])
def test_horizon_bounds(tmp_path: Path, days: int) -> None:
    with pytest.raises(ConfigError, match=r"horizon\.days"):
        load_config(_write(tmp_path, _with(horizon={"days": days})))


def test_channel_handle_format(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"youtube\.channel_handle: must look like @handle"):
        load_config(_write(tmp_path, _with(youtube__channel_handle="minnehahaumc")))


def test_plain_calendar_url_warns(tmp_path: Path) -> None:
    _, warnings = load_config(
        _write(tmp_path, _with(calendar__url="https://calendar.google.com/x/basic.ics"))
    )
    assert any("calendar.url is a plain string" in w for w in warnings)


def test_calendar_url_must_be_https(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="https"):
        load_config(_write(tmp_path, _with(calendar__url="http://insecure/basic.ics")))


def test_backup_dir_absolute_and_keep(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="backup"):
        load_config(_write(tmp_path, _with(backup={"dir": "relative/dir"})))
    with pytest.raises(ConfigError, match="backup"):
        load_config(_write(tmp_path, _with(backup={"keep": 0})))


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")
