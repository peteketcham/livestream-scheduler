from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from livestream_scheduler.secretscan import scan

SEED = Path(__file__).parents[2] / "examples" / "config-repo"


def _seed(tmp_path: Path) -> Path:
    d = tmp_path / "config"
    shutil.copytree(SEED, d)
    return d


def test_clean_seed_passes(tmp_path: Path) -> None:
    assert scan(_seed(tmp_path)) == []


@pytest.mark.parametrize(
    "name", ["credentials/calendar-url", "client_secret.json", "templates/token.json", "x.age"]
)
def test_secret_like_files_fail(tmp_path: Path, name: str) -> None:
    d = _seed(tmp_path)
    (d / name).parent.mkdir(parents=True, exist_ok=True)
    (d / name).write_text("x")
    problems = scan(d)
    assert len(problems) == 1
    assert name.split("/")[0] in problems[0]
    assert "secrets belong in credentials, not the config repo" in problems[0]


@pytest.mark.parametrize(
    "value",
    [
        "https://calendar.google.com/calendar/ical/abc/private-0123/basic.ics",
        "ya29.a0AfH6SMB",
        "GOCSPX-abc123",
    ],
)
def test_secret_like_values_fail(tmp_path: Path, value: str) -> None:
    d = _seed(tmp_path)
    cfg = d / "config.yaml"
    cfg.write_text(cfg.read_text() + f"\n# leaked: {value}\n")
    problems = scan(d)
    assert problems and "config.yaml" in problems[0]


def test_git_dir_is_ignored(tmp_path: Path) -> None:
    d = _seed(tmp_path)
    (d / ".git").mkdir()
    (d / ".git" / "token.json").write_text("x")
    assert scan(d) == []
