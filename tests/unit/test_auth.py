from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from livestream_scheduler import auth
from livestream_scheduler.config import Config
from livestream_scheduler.db.repo import Repo
from livestream_scheduler.youtube.fake import MINNEHAHA, FakeYouTube
from livestream_scheduler.youtube.port import Channel
from tests.harness import Env, FakeCreds


def _connect(env: Env, channel: Channel, cfg: Config | None = None) -> list[str]:
    revoked: list[str] = []
    repo: Repo = env.repo()
    auth.connect(
        cfg or env.config(),
        repo,
        env.state,
        consent=FakeCreds,
        youtube_for=lambda creds: FakeYouTube(channel),
        revoke_fn=revoked.append,
    )
    return revoked


def test_connect_stores_private_token_and_connection(env: Env) -> None:
    _connect(env, MINNEHAHA)
    token = env.state / "token.json"
    assert stat.S_IMODE(token.stat().st_mode) == 0o600
    assert json.loads(token.read_text())["refresh_token"] == "fake-refresh"
    conn = env.repo().get_connection()
    assert conn is not None
    assert (conn.channel_id, conn.channel_handle, conn.status) == (
        MINNEHAHA.id,
        "@minnehahaumc",
        "connected",
    )


def test_handle_match_is_case_insensitive(env: Env) -> None:
    _connect(env, Channel(MINNEHAHA.id, "Minnehaha UMC", "@MinnehahaUMC"))
    assert env.repo().get_connection() is not None


def test_wrong_channel_is_refused_and_token_revoked(env: Env) -> None:
    other = Channel("UCother", "Pete's Gaming", "@petegames")
    with pytest.raises(auth.ConnectError) as e:
        _connect(env, other)
    assert e.value.code == 3
    assert str(e.value) == (
        'Authorized channel "Pete\'s Gaming" (@petegames) is not @minnehahaumc; '
        "re-run connect and pick the right channel."
    )
    assert not (env.state / "token.json").exists()
    assert env.repo().get_connection() is None


def test_wrong_channel_revokes(env: Env) -> None:
    revoked: list[str] = []
    with pytest.raises(auth.ConnectError):
        auth.connect(
            env.config(),
            env.repo(),
            env.state,
            consent=FakeCreds,
            youtube_for=lambda c: FakeYouTube(Channel("UCx", "X", "@x")),
            revoke_fn=revoked.append,
        )
    assert revoked == ["fake-refresh"]


def test_channel_id_pin_is_enforced(env: Env) -> None:
    env.write_config(youtube={"channel_handle": "@minnehahaumc", "channel_id": "UCpinned"})
    with pytest.raises(auth.ConnectError, match="is not @minnehahaumc"):
        _connect(env, MINNEHAHA)


def test_disconnect_revokes_and_deletes(env: Env) -> None:
    _connect(env, MINNEHAHA)
    revoked: list[str] = []
    assert auth.disconnect(env.repo(), env.state, revoke_fn=revoked.append)
    assert revoked == ["fake-refresh"]
    assert not (env.state / "token.json").exists()
    assert env.repo().get_connection() is None


def test_client_config_must_be_desktop_app(env: Env, tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"web": {"client_id": "x"}}))
    bad.chmod(0o600)
    env.write_config(google={"client_secret": {"file": str(bad)}})
    with pytest.raises(auth.ConnectError, match="Desktop app"):
        auth.client_config(env.config())


def test_group_readable_token_is_refused(env: Env) -> None:
    env.connect_offline()
    (env.state / "token.json").chmod(0o640)
    from livestream_scheduler.paths import InsecurePermissionsError

    with pytest.raises(InsecurePermissionsError):
        auth.load_credentials(env.state)
