"""UTC timestamp helpers. Storage format: YYYY-MM-DDTHH:MM:SSZ."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("naive datetime")
    return dt.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def from_iso(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def rfc3339(dt: datetime) -> str:
    """YouTube API timestamp format."""
    return to_iso(dt).replace("Z", ".000Z")


def parse_api_time(value: str) -> datetime:
    """Parse YouTube's RFC 3339 timestamps (with or without fractional seconds)."""
    v = value.replace("Z", "+00:00")
    return datetime.fromisoformat(v).astimezone(UTC).replace(microsecond=0)
