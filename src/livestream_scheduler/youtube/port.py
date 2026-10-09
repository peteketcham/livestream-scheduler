"""The only boundary the sync engine uses to talk to YouTube (contracts/youtube-port.md)."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from ..timeutil import to_iso


@dataclass(frozen=True)
class Channel:
    id: str
    title: str
    handle: str  # e.g. "@minnehahaumc" (snippet.customUrl)


def _norm_description(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def managed_hash(
    title: str, description: str, start_utc: datetime, end_utc: datetime, privacy: str
) -> str:
    """Hash of exactly the fields this app manages (research R6)."""
    payload = "\x1f".join(
        [title, _norm_description(description), to_iso(start_utc), to_iso(end_utc), privacy]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BroadcastSpec:
    title: str
    description: str
    start_utc: datetime
    end_utc: datetime
    privacy: str
    made_for_kids: bool = False
    auto_start: bool = False
    auto_stop: bool = False
    dvr: bool = True

    def managed_hash(self) -> str:
        return managed_hash(
            self.title, self.description, self.start_utc, self.end_utc, self.privacy
        )


@dataclass(frozen=True)
class Broadcast:
    id: str
    channel_id: str
    title: str
    description: str
    start_utc: datetime
    end_utc: datetime | None
    privacy: str
    published_at: datetime
    life_cycle_status: str
    made_for_kids: bool = False
    auto_start: bool = False
    auto_stop: bool = False
    dvr: bool = True
    extra: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def url(self) -> str:
        return f"https://youtu.be/{self.id}"

    def managed_hash(self) -> str:
        return managed_hash(
            self.title,
            self.description,
            self.start_utc,
            self.end_utc or self.start_utc,
            self.privacy,
        )


# ---- errors (the only exceptions adapters may raise) ------------------------------------
class YouTubeError(Exception):
    """Base class for adapter errors."""


class AuthError(YouTubeError):
    """Token invalid/revoked/expired: connection → needs_reauth."""


class ChannelMismatchError(YouTubeError):
    """The token resolves to a different channel than the connected one."""


class NotEligibleError(YouTubeError):
    """The channel cannot live stream (liveStreamingNotEnabled, livePermissionBlocked)."""


class QuotaExceededError(YouTubeError):
    """Daily/rate quota hit: stop writes, defer the rest."""


class TransientError(YouTubeError):
    """5xx/timeouts after in-call retries."""


class BroadcastNotFoundError(YouTubeError):
    """404 / liveBroadcastNotFound."""


class InvalidRequestError(YouTubeError):
    """400-class validation errors for one broadcast."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(f"{reason}: {message}")
        self.reason = reason
        self.message = message


QUOTA_COST = {"list": 1, "insert": 50, "update": 50, "delete": 50, "bind": 50}


class YouTubePort(Protocol):
    quota_used: int

    def whoami(self) -> Channel: ...

    def get_broadcasts(self, ids: Sequence[str]) -> dict[str, Broadcast]: ...

    def list_upcoming(self, since: datetime | None = None) -> list[Broadcast]: ...

    def insert_broadcast(self, spec: BroadcastSpec) -> Broadcast: ...

    def update_broadcast(self, broadcast_id: str, spec: BroadcastSpec) -> Broadcast: ...

    def delete_broadcast(self, broadcast_id: str) -> None: ...

    def bind(self, broadcast_id: str, stream_id: str) -> None: ...
