"""OAuth connect/disconnect and token storage (research R9, R19)."""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from .config import Config
from .db.repo import Repo
from .paths import ensure_private
from .secrets import resolve
from .youtube.port import Channel, YouTubePort

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
TOKEN_NAME = "token.json"


class ConnectError(Exception):
    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


def token_path(state_dir: Path) -> Path:
    return state_dir / TOKEN_NAME


def client_config(cfg: Config) -> dict[str, Any]:
    raw = resolve(cfg.google.client_secret)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ConnectError("google.client_secret is not OAuth client JSON", 2) from None
    if "installed" not in data or "client_id" not in data["installed"]:
        raise ConnectError(
            'google.client_secret is not a "Desktop app" OAuth client '
            "(missing installed.client_id)",
            2,
        )
    return dict(data)


def save_token(state_dir: Path, token_json: str) -> None:
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = token_path(state_dir)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token_json)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def load_credentials(state_dir: Path) -> Any | None:
    """google.oauth2.credentials.Credentials, or None when not connected."""
    path = token_path(state_dir)
    if not path.is_file():
        return None
    ensure_private(path)
    from google.oauth2.credentials import Credentials

    return Credentials.from_authorized_user_file(str(path), SCOPES)  # type: ignore[no-untyped-call]


def run_consent(config: dict[str, Any], *, open_browser: bool, port: int | None) -> Any:
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_config(config, SCOPES)
    return flow.run_local_server(
        host="localhost",
        port=port or 0,
        open_browser=open_browser,
        access_type="offline",
        prompt="consent",
        authorization_prompt_message="Open this URL in a browser and choose the channel: {url}",
        success_message="Connected. You can close this window.",
    )


def revoke(token: str, http: Callable[..., Any] = requests.post) -> None:
    # Best effort; the local token is removed regardless.
    with contextlib.suppress(requests.RequestException):
        http(REVOKE_URL, params={"token": token}, timeout=15)


def handles_match(a: str, b: str) -> bool:
    return a.strip().lstrip("@").casefold() == b.strip().lstrip("@").casefold()


def connect(
    cfg: Config,
    repo: Repo,
    state_dir: Path,
    *,
    consent: Callable[[], Any],
    youtube_for: Callable[[Any], YouTubePort],
    revoke_fn: Callable[[str], None] = revoke,
    forget_tracked: bool = False,
) -> Channel:
    """Run consent, verify the channel, then store token + connection."""
    creds = consent()
    yt = youtube_for(creds)
    channel = yt.whoami()
    wanted = cfg.youtube.channel_handle
    if not handles_match(channel.handle, wanted) or (
        cfg.youtube.channel_id and channel.id != cfg.youtube.channel_id
    ):
        token = getattr(creds, "refresh_token", None) or getattr(creds, "token", None)
        if token:
            revoke_fn(token)
        raise ConnectError(
            f'Authorized channel "{channel.title}" ({channel.handle}) is not {wanted}; '
            "re-run connect and pick the right channel.",
            3,
        )
    existing = repo.get_connection()
    if existing and existing.channel_id != channel.id and not forget_tracked:
        tracked = repo.conn.execute(
            "SELECT COUNT(*) FROM broadcast WHERE deleted_at IS NULL"
        ).fetchone()[0]
        if tracked:
            raise ConnectError(
                f"{tracked} livestreams are tracked for channel {existing.channel_handle}; "
                "use --forget-tracked to switch channels",
                2,
            )
    save_token(state_dir, creds.to_json())
    with repo.tx():
        repo.save_connection(channel.id, channel.title, channel.handle)
    return channel


def disconnect(repo: Repo, state_dir: Path, revoke_fn: Callable[[str], None] = revoke) -> bool:
    path = token_path(state_dir)
    had = path.is_file()
    if had:
        try:
            data = json.loads(path.read_text())
            token = data.get("refresh_token") or data.get("token")
            if token:
                revoke_fn(token)
        except (OSError, json.JSONDecodeError):
            pass
        path.unlink()
    with repo.tx():
        repo.delete_connection()
    return had
