# Contract: `YouTubePort` (internal boundary to YouTube Data API v3)

The sync engine depends only on this protocol. `GoogleYouTube` implements it against the real API, and `FakeYouTube` is an in-memory implementation for tests. Both must pass the same contract test suite (`tests/contract/test_youtube_port.py`).

```python
class YouTubePort(Protocol):
    def whoami(self) -> Channel: ...                                   # channels.list(part=snippet, mine=true); Channel has id, title, handle (snippet.customUrl)
    def get_broadcasts(self, ids: Sequence[str]) -> dict[str, Broadcast]: ...   # liveBroadcasts.list(id=…), ≤50/call; missing ids absent
    def list_upcoming(self, since: datetime | None = None) -> list[Broadcast]: ...   # liveBroadcasts.list(mine=true, broadcastStatus=upcoming) — read-only: R5 recovery + 004 S6 duplicate check
    def insert_broadcast(self, spec: BroadcastSpec) -> Broadcast: ...  # liveBroadcasts.insert(part=snippet,status,contentDetails)
    def update_broadcast(self, id: str, spec: BroadcastSpec) -> Broadcast: ...  # read-merge-write; liveBroadcasts.update
    def delete_broadcast(self, id: str) -> None: ...                   # liveBroadcasts.delete; 404 → BroadcastNotFound
    def bind(self, broadcast_id: str, stream_id: str) -> None: ...     # liveBroadcasts.bind (only if youtube.stream_id set)
```

`BroadcastSpec` fields are `title`, `description`, `start_utc`, `end_utc`, `privacy`, `made_for_kids`, `auto_start`, `auto_stop`, `dvr`. `Broadcast` adds `id`, `channel_id`, `published_at`, `life_cycle_status`, `url`, and `managed_hash()`, which is computed over exactly the `BroadcastSpec` fields as YouTube echoes them back. Hashing is normalized: times are compared at second precision in UTC, and descriptions are compared after YouTube's newline normalization.

## Error contract

All adapter methods raise only these exceptions:

| Exception | Raised for (API reason / status) | Engine behavior |
|---|---|---|
| `AuthError` | 401, `invalid_grant`, `authError`, refresh failure | Abort run, connection → `needs_reauth`, notify |
| `ChannelMismatch` | `whoami().id` ≠ connected channel | Abort run, `needs_reauth`, notify |
| `NotEligible` | `liveStreamingNotEnabled`, `livePermissionBlocked` | Abort run, connection → `not_eligible`, notify with explanation |
| `QuotaExceeded` | `quotaExceeded`, `dailyLimitExceeded`, `rateLimitExceeded`, `userRequestsExceedRateLimit` | Stop writes, defer remaining (R8) |
| `TransientError` | 5xx, `backendError`, timeouts, connection reset | Retry ×3 with backoff, then defer |
| `BroadcastNotFound` | 404 / `liveBroadcastNotFound` | → `owner_deleted` |
| `InvalidRequest(reason, message)` | 400s such as `invalidScheduledStartTime`, `invalidTitle`, `invalidDescription`, `invalidPrivacyStatus` | Occurrence → `failed` with mapped plain-language reason |

## Quota accounting (estimates recorded in `run.quota_units_est`)

| Call | Units |
|---|---|
| `channels.list`, `liveBroadcasts.list` | 1 |
| `liveBroadcasts.insert` / `update` / `delete` / `bind` | 50 |

## Invariants checked by contract tests

1. `insert` followed by `get_broadcasts([id])` returns an equal `managed_hash()`.
2. `update` touches only the managed fields. Other snippet and contentDetails values set out of band (e.g. a thumbnail, a monitor stream) are preserved.
3. `delete` of an unknown id raises `BroadcastNotFound`, and never another error.
4. `get_broadcasts` of a deleted id returns no entry for it.
5. `list_upcoming` returns only broadcasts of the authenticated channel, including ones not created by this app. Their ids are never passed to `update_broadcast`, `delete_broadcast` or `bind` (enforced by the engine's ownership rule and by a contract test).
6. No method accepts or returns OAuth tokens. `repr()` of the adapter contains no secrets.
