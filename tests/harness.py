"""Integration-test harness: a config + state dir + FakeYouTube wired into run_sync / the CLI."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import time_machine
import yaml
from click.testing import CliRunner, Result

from livestream_scheduler import cli as cli_mod
from livestream_scheduler.config import Config, load_config
from livestream_scheduler.db.migrate import open_db
from livestream_scheduler.db.repo import Repo
from livestream_scheduler.sync.run import SyncOptions, SyncReport, run_sync
from livestream_scheduler.youtube.fake import FakeYouTube
from livestream_scheduler.youtube.port import Channel

FIXTURES = Path(__file__).parent / "fixtures"

FAKE_TOKEN = {
    "token": "fake-access",
    "refresh_token": "fake-refresh",
    "client_id": "fake-client.apps.googleusercontent.com",
    "client_secret": "fake-secret",
    "token_uri": "https://oauth2.googleapis.com/token",
}

CLIENT_JSON = {
    "installed": {
        "client_id": "fake-client.apps.googleusercontent.com",
        "client_secret": "fake-secret",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}


class FakeCreds:
    def __init__(self) -> None:
        self.refresh_token = "fake-refresh"
        self.token = "fake-access"

    def to_json(self) -> str:
        return json.dumps(FAKE_TOKEN)


@dataclass
class Env:
    root: Path
    yt: FakeYouTube = field(default_factory=FakeYouTube)
    extra_config: dict[str, Any] = field(default_factory=dict)

    @property
    def state(self) -> Path:
        return self.root / "state"

    @property
    def config_path(self) -> Path:
        return self.root / "config" / "config.yaml"

    @property
    def calendar(self) -> Path:
        return self.root / "config" / "calendar.ics"

    def write_config(self, **extra: Any) -> None:
        data: dict[str, Any] = {
            "google": {"client_secret": {"file": str(self.root / "client.json")}},
            "calendar": {"path": "calendar.ics"},
            "defaults": {"timezone": "America/Chicago"},
            "youtube": {"channel_handle": "@minnehahaumc"},
            "notify": {
                "email_to": "owner@example.org",
                "email_from": "scheduler@example.org",
                "smtp_host": "localhost",
            },
        }
        data.update(self.extra_config)
        data.update(extra)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(yaml.safe_dump(data))
        client = self.root / "client.json"
        client.write_text(json.dumps(CLIENT_JSON))
        os.chmod(client, 0o600)

    def use_calendar(self, name: str) -> None:
        shutil.copyfile(FIXTURES / "ics" / name, self.calendar)

    def write_calendar(self, text: str) -> None:
        self.calendar.write_text(text)

    def config(self) -> Config:
        return load_config(self.config_path)[0]

    def repo(self) -> Repo:
        return Repo(open_db(self.state))

    def connect_offline(self, channel: Channel | None = None) -> None:
        """Pretend `connect` already happened: token + connection row."""
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        token = self.state / "token.json"
        token.write_text(json.dumps(FAKE_TOKEN))
        os.chmod(token, 0o600)
        ch = channel or self.yt.channel
        repo = self.repo()
        with repo.tx():
            repo.save_connection(ch.id, ch.title, ch.handle)
        repo.conn.close()

    def sync(self, now: datetime, after_run: Any = None, **opts: Any) -> SyncReport:
        with time_machine.travel(now, tick=False):
            return run_sync(
                self.config(),
                self.state,
                youtube_factory=lambda creds: self.yt,
                options=SyncOptions(**opts),
                config_dir=self.config_path.parent,
                after_run=after_run,
            )

    def cli(self, *args: str, now: datetime | None = None, yt: FakeYouTube | None = None) -> Result:
        target = yt or self.yt
        cli_mod.YOUTUBE_FACTORY = lambda creds: target
        cli_mod.CONSENT = lambda client, open_browser, port: FakeCreds()
        argv = ["--config", str(self.config_path), "--state-dir", str(self.state), *args]
        if now is None:
            return _invoke_main(argv)
        with time_machine.travel(now, tick=False):
            return _invoke_main(argv)


def _invoke_main(argv: list[str]) -> Result:
    """Run the real entry point (exit codes included) under CliRunner's output capture."""
    import click

    cmd = click.Command("main", callback=lambda: cli_mod.main(argv))
    return CliRunner().invoke(cmd, [], catch_exceptions=False)
