"""Command-line interface (contracts/cli.md)."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any

import click

from . import paths
from .config import Config, ConfigError, load_config
from .logging import setup_logging


class ExitCode(IntEnum):
    OK = 0
    PARTIAL = 1
    USAGE = 2
    NOT_CONNECTED = 3
    FEED = 4
    SAFETY_HOLD = 5
    INTERNAL = 10


class CliError(Exception):
    """An error with a user-facing message and a specific exit code."""

    def __init__(self, message: str, code: ExitCode) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class Ctx:
    config_path: Path
    state_dir: Path
    json: bool
    _config: Config | None = None
    _warnings: list[str] | None = None

    def config(self) -> Config:
        if self._config is None:
            try:
                self._config, self._warnings = load_config(self.config_path)
            except ConfigError as e:
                raise CliError(str(e), ExitCode.USAGE) from None
        return self._config

    def warnings(self) -> list[str]:
        self.config()
        return self._warnings or []


def emit(ctx: Ctx, human: str, data: dict[str, Any]) -> None:
    if ctx.json:
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        click.echo(human)


@click.group()
@click.option("--config", "config_opt", default=None, help="Path to config.yaml")
@click.option("--state-dir", "state_opt", default=None, help="State directory")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output")
@click.option("-v", "--verbose", count=True)
@click.option("-q", "--quiet", is_flag=True)
@click.pass_context
def cli(
    click_ctx: click.Context,
    config_opt: str | None,
    state_opt: str | None,
    as_json: bool,
    verbose: int,
    quiet: bool,
) -> None:
    """Schedule YouTube livestreams from a calendar feed."""
    setup_logging(-1 if quiet else verbose)
    click_ctx.obj = Ctx(
        config_path=paths.config_path(config_opt),
        state_dir=paths.state_dir(state_opt),
        json=as_json,
    )


def main(argv: list[str] | None = None) -> None:
    try:
        cli.main(args=argv, standalone_mode=False)
    except CliError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(int(e.code))
    except click.exceptions.Abort:
        sys.exit(int(ExitCode.USAGE))
    except click.ClickException as e:
        e.show()
        sys.exit(int(ExitCode.USAGE))
    except Exception as e:  # pragma: no cover - last resort
        from .logging import redact

        click.echo(f"internal error: {redact(str(e))}", err=True)
        sys.exit(int(ExitCode.INTERNAL))
    sys.exit(int(ExitCode.OK))
