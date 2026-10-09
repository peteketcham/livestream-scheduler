"""Fetch the calendar feed (research R1). The secret URL is never logged or stored."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import requests

from ..config import Config
from ..db.repo import Repo
from ..logging import RedactingFilter
from ..secrets import SecretError, resolve
from ..timeutil import to_iso, utcnow
from .expand import FeedError

TIMEOUT = 15
CACHE_NAME = "feed-cache.ics"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_private(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def fetch_feed(
    cfg: Config,
    repo: Repo,
    state_dir: Path,
    *,
    persist: bool = True,
    session: requests.Session | None = None,
    config_dir: Path | None = None,
) -> bytes:
    """Return the ICS bytes or raise FeedError (callers must then plan no removals)."""
    if cfg.calendar.path is not None:
        path = Path(cfg.calendar.path).expanduser()
        if not path.is_absolute() and config_dir is not None:
            path = config_dir / path
        try:
            return path.read_bytes()
        except OSError as e:
            raise FeedError(f"cannot read calendar file {path}: {e.strerror}") from None

    assert cfg.calendar.url is not None
    try:
        url = resolve(cfg.calendar.url)
    except SecretError as e:
        raise FeedError(f"calendar.url: {e}") from None
    RedactingFilter.register(url)
    url_hash = _sha(url.encode())
    source = repo.get_calendar_source()
    cache = state_dir / CACHE_NAME
    headers = {"User-Agent": "livestream-scheduler"}
    if source and source.url_hash == url_hash and cache.is_file():
        if source.etag:
            headers["If-None-Match"] = source.etag
        if source.last_modified:
            headers["If-Modified-Since"] = source.last_modified

    http = session or requests.Session()
    try:
        resp = http.get(url, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise FeedError(f"calendar feed could not be fetched ({type(e).__name__})") from None
    if resp.status_code == 304:
        body = cache.read_bytes()
    elif resp.status_code == 200:
        body = resp.content
    else:
        raise FeedError(f"calendar feed returned HTTP {resp.status_code}")
    if b"BEGIN:VCALENDAR" not in body[:2048]:
        raise FeedError("calendar feed did not return iCalendar data")

    if persist:
        if resp.status_code == 200:
            _write_private(cache, body)
        repo.save_calendar_source(
            url_hash=url_hash,
            etag=resp.headers.get("ETag"),
            last_modified=resp.headers.get("Last-Modified"),
            last_fetched_at=to_iso(utcnow()),
            last_body_sha256=_sha(body),
        )
    return body
