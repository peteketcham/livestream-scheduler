from __future__ import annotations

import json
from typing import Any

import httplib2
import pytest

from livestream_scheduler.youtube.google_adapter import GoogleYouTube
from livestream_scheduler.youtube.port import (
    AuthError,
    BroadcastNotFoundError,
    InvalidRequestError,
    NotEligibleError,
    QuotaExceededError,
    TransientError,
)


class ErrorHttp:
    def __init__(self, status: int, reason: str, times: int = 99) -> None:
        self.status, self.reason, self.times, self.calls = status, reason, times, 0

    def request(self, uri: str, method: str = "GET", **_: Any) -> tuple[Any, bytes]:
        self.calls += 1
        if self.calls <= self.times:
            body = {
                "error": {"code": self.status, "message": "m", "errors": [{"reason": self.reason}]}
            }
            return httplib2.Response({"status": self.status}), json.dumps(body).encode()
        return httplib2.Response({"status": 200}), b'{"items": []}'


@pytest.mark.parametrize(
    ("status", "reason", "exc"),
    [
        (403, "quotaExceeded", QuotaExceededError),
        (403, "userRequestsExceedRateLimit", QuotaExceededError),
        (403, "liveStreamingNotEnabled", NotEligibleError),
        (401, "authError", AuthError),
        (404, "liveBroadcastNotFound", BroadcastNotFoundError),
        (400, "invalidScheduledStartTime", InvalidRequestError),
    ],
)
def test_error_mapping(status: int, reason: str, exc: type[Exception]) -> None:
    yt = GoogleYouTube(http=ErrorHttp(status, reason), sleep=lambda s: None)
    with pytest.raises(exc):
        yt.delete_broadcast("abc")


def test_server_errors_retried_then_transient() -> None:
    http = ErrorHttp(503, "backendError")
    yt = GoogleYouTube(http=http, sleep=lambda s: None)
    with pytest.raises(TransientError):
        yt.get_broadcasts(["a"])
    assert http.calls == 4  # 1 + 3 retries


def test_server_error_recovers_within_retries() -> None:
    http = ErrorHttp(500, "backendError", times=2)
    yt = GoogleYouTube(http=http, sleep=lambda s: None)
    assert yt.get_broadcasts(["a"]) == {}


def test_invalid_request_carries_reason() -> None:
    yt = GoogleYouTube(http=ErrorHttp(400, "invalidTitle"), sleep=lambda s: None)
    with pytest.raises(InvalidRequestError) as e:
        yt.delete_broadcast("x")
    assert e.value.reason == "invalidTitle"
