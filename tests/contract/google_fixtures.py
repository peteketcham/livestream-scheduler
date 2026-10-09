"""An offline emulator of the YouTube Data API v3 endpoints GoogleYouTube uses.

It plays the role of recorded HTTP: GoogleYouTube builds real googleapiclient requests from
the bundled discovery document, and this object answers them like the API does.
"""

from __future__ import annotations

import itertools
import json
from typing import Any
from urllib.parse import parse_qs, urlparse

import httplib2

from livestream_scheduler.youtube.google_adapter import GoogleYouTube

CHANNEL = {
    "id": "UCzwZQ34D3RZEncTf6fAe0hQ",
    "snippet": {"title": "Minnehaha UMC", "customUrl": "@minnehahaumc"},
}


def _error(status: int, reason: str, message: str) -> tuple[httplib2.Response, bytes]:
    body = {"error": {"code": status, "message": message, "errors": [{"reason": reason}]}}
    return httplib2.Response({"status": status}), json.dumps(body).encode()


class EmulatedYouTubeHttp:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.requests: list[tuple[str, str]] = []
        self._ids = (f"emu{n:04d}" for n in itertools.count(1))

    def request(
        self,
        uri: str,
        method: str = "GET",
        body: Any = None,
        headers: Any = None,
        **_: Any,
    ) -> tuple[httplib2.Response, bytes]:
        parsed = urlparse(uri)
        path = parsed.path.removeprefix("/youtube/v3/")
        q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        self.requests.append((method, path))
        payload = json.loads(body) if body else {}
        if path == "channels" and method == "GET":
            return self._ok({"items": [CHANNEL]})
        if path == "liveBroadcasts" and method == "GET":
            if "id" in q:
                ids = q["id"].split(",")
                return self._ok({"items": [self.items[i] for i in ids if i in self.items]})
            ups = [
                i
                for i in self.items.values()
                if i["status"]["lifeCycleStatus"] in ("created", "ready")
            ]
            return self._ok({"items": ups})
        if path == "liveBroadcasts" and method == "POST":
            bid = next(self._ids)
            item = self._item(bid, payload)
            self.items[bid] = item
            return self._ok(item)
        if path == "liveBroadcasts" and method == "PUT":
            bid = payload.get("id")
            if bid not in self.items:
                return _error(404, "liveBroadcastNotFound", "Broadcast not found")
            if "monitorStream" not in payload.get("contentDetails", {}):
                return _error(400, "invalidMonitorStream", "monitorStream is required")
            item = self._item(bid, payload, published=self.items[bid]["snippet"]["publishedAt"])
            self.items[bid] = item
            return self._ok(item)
        if path == "liveBroadcasts" and method == "DELETE":
            if q.get("id") not in self.items:
                return _error(404, "liveBroadcastNotFound", "Broadcast not found")
            del self.items[q["id"]]
            return httplib2.Response({"status": 204}), b""
        if path == "liveBroadcasts/bind" and method == "POST":
            return self._ok(self.items.get(q.get("id", ""), {}))
        return _error(400, "badRequest", f"unexpected {method} {path}")

    @staticmethod
    def _ok(data: dict[str, Any]) -> tuple[httplib2.Response, bytes]:
        return httplib2.Response({"status": 200}), json.dumps(data).encode()

    @staticmethod
    def _item(
        bid: str, payload: dict[str, Any], published: str = "2026-10-08T12:00:00Z"
    ) -> dict[str, Any]:
        sn = payload["snippet"]
        st = payload["status"]
        return {
            "kind": "youtube#liveBroadcast",
            "id": bid,
            "snippet": {
                "publishedAt": published,
                "channelId": CHANNEL["id"],
                "title": sn["title"],
                "description": sn.get("description", ""),
                "scheduledStartTime": sn["scheduledStartTime"].replace(".000Z", "Z"),
                "scheduledEndTime": sn.get("scheduledEndTime", "").replace(".000Z", "Z"),
            },
            "status": {
                "lifeCycleStatus": "created",
                "privacyStatus": st["privacyStatus"],
                "selfDeclaredMadeForKids": st.get("selfDeclaredMadeForKids", False),
            },
            "contentDetails": payload.get("contentDetails", {}),
        }


def google_adapter_factory() -> GoogleYouTube:
    return GoogleYouTube(http=EmulatedYouTubeHttp(), sleep=lambda s: None)
