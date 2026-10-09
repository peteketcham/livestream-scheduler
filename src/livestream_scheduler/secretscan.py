"""Refuse secret material in the config repository (research R17, FR-022, SC-009)."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

FILE_PATTERNS = ("client_secret*.json", "token*.json", "*.age")
DIR_NAMES = ("credentials",)
VALUE_PATTERNS = (
    re.compile(r"https?://\S*/ical/\S*", re.I),
    re.compile(r"private-[0-9a-f]{3,}", re.I),
    re.compile(r"ya29\.[A-Za-z0-9_\-]+"),
    re.compile(r"GOCSPX-[A-Za-z0-9_\-]+"),
)
TEXT_SUFFIXES = (".yaml", ".yml", ".j2", ".txt", ".md")
HINT = "secrets belong in credentials, not the config repo"


def scan(config_dir: Path) -> list[str]:
    problems: list[str] = []
    for path in sorted(config_dir.rglob("*")):
        rel = path.relative_to(config_dir)
        if rel.parts and rel.parts[0] == ".git":
            continue
        if path.is_dir():
            if path.name in DIR_NAMES:
                problems.append(f"config dir contains secret-like directory {rel}/; {HINT}")
            continue
        if any(part in DIR_NAMES for part in rel.parts[:-1]):
            continue  # already reported via its directory
        if any(fnmatch.fnmatch(path.name, pat) for pat in FILE_PATTERNS):
            problems.append(f"config dir contains secret-like file {rel}; {HINT}")
            continue
        if path.suffix in TEXT_SUFFIXES:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for pat in VALUE_PATTERNS:
                if pat.search(text):
                    problems.append(
                        f"{rel} contains a secret-like value ({pat.pattern[:12]}…); {HINT}"
                    )
                    break
    return problems
