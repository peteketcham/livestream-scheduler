"""YouTubePort backed by YouTube Data API v3 (contracts/youtube-port.md, research R4/R8)."""

from __future__ import annotations

import json
import logging
import random
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from ..timeutil import parse_api_time, rfc3339
from .port import (
    QUOTA_COST,
    AuthError,
    Broadcast,
    BroadcastNotFoundError,
    BroadcastSpec,
    Channel,
    InvalidRequestError,
    NotEligibleError,
    QuotaExceededError,
    TransientError,
)

log = logging.getLogger(__name__)

PARTS = "id,snippet,status,contentDetails"
QUOTA_REASONS = {
    "quotaExceeded",
    "dailyLimitExceeded",
    "rateLimitExceeded",
    "userRateLimitExceeded",
    "userRequestsExceedRateLimit",
}
NOT_ELIGIBLE_REASONS = {
    "liveStreamingNotEnabled",
    "livePermissionBlocked",
    "insufficientLivePermissions",
}
AUTH_REASONS = {"authError", "invalid_grant", "unauthorized", "forbidden_token"}
RETRIES = 3


def _reason(err: Any) -> tuple[int, str, str]:
    status = int(getattr(getattr(err, "resp", None), "status", 0) or 0)
    reason, message = "", str(err)
    try:
        payload = json.loads(err.content.decode("utf-8"))
        e = payload.get("error", {})
        message = e.get("message", message)
        errors = e.get("errors") or []
        if errors:
            reason = errors[0].get("reason", "")
        reason = reason or e.get("status", "")
    except Exception:
        pass
    return status, reason, message


class GoogleYouTube:
    def __init__(
        self,
        credentials: Any = None,
        *,
        http: Any = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        from googleapiclient.discovery import build

        kwargs: dict[str, Any] = {"cache_discovery": False, "static_discovery": True}
        if http is not None:
            kwargs["http"] = http
        else:
            kwargs["credentials"] = credentials
        self._svc = build("youtube", "v3", **kwargs)
        self._sleep = sleep
        self.quota_used = 0

    def __repr__(self) -> str:
        return "GoogleYouTube()"

    # ---- plumbing -------------------------------------------------------------------------
    def _execute(self, request: Any, cost_key: str) -> Any:
        from googleapiclient.errors import HttpError

        try:
            from google.auth.exceptions import RefreshError
        except ImportError:  # pragma: no cover
            RefreshError = Exception  # type: ignore[assignment,misc]

        delay = 1.0
        for attempt in range(RETRIES + 1):
            try:
                self.quota_used += QUOTA_COST[cost_key]
                return request.execute(num_retries=0)
            except RefreshError as e:
                raise AuthError("token refresh failed") from e
            except HttpError as e:
                status, reason, message = _reason(e)
                if status == 401 or reason in AUTH_REASONS:
                    raise AuthError(reason or "unauthorized") from e
                if reason in QUOTA_REASONS:
                    raise QuotaExceededError(reason) from e
                if reason in NOT_ELIGIBLE_REASONS:
                    raise NotEligibleError(reason) from e
                if status == 404 or reason in ("liveBroadcastNotFound", "notFound"):
                    raise BroadcastNotFoundError(reason or "notFound") from e
                if status >= 500 or reason == "backendError":
                    if attempt < RETRIES:
                        self._backoff(delay)
                        delay *= 2
                        continue
                    raise TransientError(f"{status} {reason}") from e
                raise InvalidRequestError(reason or str(status), message) from e
            except (TimeoutError, ConnectionError, OSError) as e:
                if attempt < RETRIES:
                    self._backoff(delay)
                    delay *= 2
                    continue
                raise TransientError(type(e).__name__) from e
        raise TransientError("retries exhausted")  # pragma: no cover

    def _backoff(self, delay: float) -> None:
        self._sleep(delay + random.uniform(0, delay / 2))

    @staticmethod
    def _parse(item: dict[str, Any]) -> Broadcast:
        sn = item.get("snippet", {})
        st = item.get("status", {})
        cd = item.get("contentDetails", {})
        end = sn.get("scheduledEndTime")
        return Broadcast(
            id=item["id"],
            channel_id=sn.get("channelId", ""),
            title=sn.get("title", ""),
            description=sn.get("description", ""),
            start_utc=parse_api_time(sn["scheduledStartTime"]),
            end_utc=parse_api_time(end) if end else None,
            privacy=st.get("privacyStatus", ""),
            published_at=parse_api_time(sn.get("publishedAt", sn["scheduledStartTime"])),
            life_cycle_status=st.get("lifeCycleStatus", ""),
            made_for_kids=bool(st.get("selfDeclaredMadeForKids", False)),
            auto_start=bool(cd.get("enableAutoStart", False)),
            auto_stop=bool(cd.get("enableAutoStop", False)),
            dvr=bool(cd.get("enableDvr", True)),
            extra={"raw": item},
        )

    @staticmethod
    def _body(spec: BroadcastSpec, current: dict[str, Any] | None = None) -> dict[str, Any]:
        cur = current or {}
        snippet = {
            **{k: v for k, v in cur.get("snippet", {}).items() if k in ("thumbnails",)},
            "title": spec.title,
            "description": spec.description,
            "scheduledStartTime": rfc3339(spec.start_utc),
            "scheduledEndTime": rfc3339(spec.end_utc),
        }
        status = {
            **{k: v for k, v in cur.get("status", {}).items() if k not in ("lifeCycleStatus",)},
            "privacyStatus": spec.privacy,
            "selfDeclaredMadeForKids": spec.made_for_kids,
        }
        content = dict(cur.get("contentDetails", {}))
        content.pop("boundStreamId", None)
        content.pop("boundStreamLastUpdateTimeMs", None)
        content.setdefault(
            "monitorStream", {"enableMonitorStream": True, "broadcastStreamDelayMs": 0}
        )
        content.update(
            {
                "enableAutoStart": spec.auto_start,
                "enableAutoStop": spec.auto_stop,
                "enableDvr": spec.dvr,
            }
        )
        body: dict[str, Any] = {"snippet": snippet, "status": status, "contentDetails": content}
        if current is not None:
            body["id"] = current["id"]
        return body

    # ---- port -----------------------------------------------------------------------------
    def whoami(self) -> Channel:
        resp = self._execute(self._svc.channels().list(part="snippet", mine=True), "list")
        items = resp.get("items") or []
        if not items:
            raise AuthError("no YouTube channel for these credentials")
        sn = items[0]["snippet"]
        handle = sn.get("customUrl", "")
        if handle and not handle.startswith("@"):
            handle = "@" + handle
        return Channel(id=items[0]["id"], title=sn.get("title", ""), handle=handle)

    def _raw(self, ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for i in range(0, len(ids), 50):
            chunk = list(ids[i : i + 50])
            req = self._svc.liveBroadcasts().list(part=PARTS, id=",".join(chunk), maxResults=50)
            for item in self._execute(req, "list").get("items", []):
                out[item["id"]] = item
        return out

    def get_broadcasts(self, ids: Sequence[str]) -> dict[str, Broadcast]:
        return {k: self._parse(v) for k, v in self._raw(ids).items()}

    def list_upcoming(self, since: datetime | None = None) -> list[Broadcast]:
        out: list[Broadcast] = []
        token: str | None = None
        while True:
            req = self._svc.liveBroadcasts().list(
                part=PARTS,
                broadcastStatus="upcoming",
                broadcastType="all",
                maxResults=50,
                pageToken=token,
            )
            resp = self._execute(req, "list")
            for item in resp.get("items", []):
                b = self._parse(item)
                if since is None or b.published_at >= since or b.start_utc >= since:
                    out.append(b)
            token = resp.get("nextPageToken")
            if not token:
                return out

    def insert_broadcast(self, spec: BroadcastSpec) -> Broadcast:
        req = self._svc.liveBroadcasts().insert(
            part="snippet,status,contentDetails", body=self._body(spec)
        )
        return self._parse(self._execute(req, "insert"))

    def update_broadcast(self, broadcast_id: str, spec: BroadcastSpec) -> Broadcast:
        current = self._raw([broadcast_id]).get(broadcast_id)
        if current is None:
            raise BroadcastNotFoundError(broadcast_id)
        req = self._svc.liveBroadcasts().update(
            part="snippet,status,contentDetails", body=self._body(spec, current)
        )
        return self._parse(self._execute(req, "update"))

    def delete_broadcast(self, broadcast_id: str) -> None:
        self._execute(self._svc.liveBroadcasts().delete(id=broadcast_id), "delete")

    def bind(self, broadcast_id: str, stream_id: str) -> None:
        req = self._svc.liveBroadcasts().bind(
            id=broadcast_id, part="id,contentDetails", streamId=stream_id
        )
        self._execute(req, "bind")
