#!/usr/bin/env bash
# Quality gates (replaces hosted CI; see constitution "Repository hygiene").
#   scripts/check.sh          full: lock check, lint, types, all non-live tests
#   scripts/check.sh --fast   pre-commit subset: lint, types, unit + contract tests
set -euo pipefail
cd "$(dirname "$0")/.."

uv sync --locked --quiet
uv run ruff check
uv run ruff format --check
uv run mypy src
if [[ "${1:-}" == "--fast" ]]; then
  uv run pytest -q tests/unit tests/contract
else
  uv run pytest -q
fi
