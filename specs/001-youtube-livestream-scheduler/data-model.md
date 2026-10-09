# Data Model: YouTube Livestream Scheduler

**Feature**: `001-youtube-livestream-scheduler` | **Date**: 2026-10-08

State lives in two places:
- **Owner-authored inputs**: the YAML config ([contracts/config-schema.md](contracts/config-schema.md)) and the calendar feed ([contracts/calendar-mapping.md](contracts/calendar-mapping.md)).
- **Application state**: SQLite at `<state_dir>/state.db`, described below. The OAuth token is *not* in SQLite. It is kept in `<state_dir>/token.json` with mode `0600` (research R9).

## Spec entity → storage mapping

| Spec entity | Realized as |
|---|---|
| Channel Connection | `channel_connection` table (single row) + `token.json` |
| Schedule | The calendar feed (events and recurrence rules) + `calendar_source` table (fetch state) + `defaults` in config |
| Occurrence | `occurrence` table |
| Livestream Event | `broadcast` table (what we wrote; ownership proof) |
| Run Record | `run` + `run_item` tables |
| *(supporting)* | `notification` table (dedup of emails) |

---

## channel_connection

Holds at most one row (`id = 1`), which enforces a single channel (FR-001).

| Field | Type | Rules |
|---|---|---|
| id | INTEGER PK | CHECK (id = 1) |
| channel_id | TEXT NOT NULL | `UC…` id from `channels.list(mine=true)` |
| channel_title | TEXT NOT NULL | Shown by `status` / `connect` |
| channel_handle | TEXT NOT NULL | e.g. `@minnehahaumc`; must equal config `youtube.channel_handle` at connect time |
| status | TEXT NOT NULL | `connected` \| `needs_reauth` \| `not_eligible` |
| status_reason | TEXT NULL | Plain-language reason |
| connected_at | TEXT (UTC ISO-8601) | |
| last_verified_at | TEXT NULL | Set on each run that confirms token → same channel_id |

**Transitions**: *(none)* → `connected` on `connect`. `connected` → `needs_reauth` on an auth error or channel-id mismatch. `connected` → `not_eligible` on `liveStreamingNotEnabled`. Any state → `connected` on a successful `connect` to the **same** channel. `disconnect` deletes the row and the token. Connecting a *different* channel while occurrences are tracked is refused unless `--forget-tracked` is given, because tracked broadcasts belong to the old channel.

## calendar_source

Holds one row and caches fetch state.

| Field | Type | Rules |
|---|---|---|
| id | INTEGER PK | CHECK (id = 1) |
| url_hash | TEXT | SHA-256 of the configured URL. The secret ICS URL itself is never stored or logged. |
| etag | TEXT NULL | For `If-None-Match` |
| last_modified | TEXT NULL | |
| last_fetched_at | TEXT NULL | |
| last_body_sha256 | TEXT NULL | If unchanged and the horizon window has not advanced, expansion can be skipped |
| last_event_count | INTEGER NULL | Used by the mass-removal guard (R7) |

## occurrence

One row per calendar event instance that has ever fallen in the window.

| Field | Type | Rules |
|---|---|---|
| id | INTEGER PK | Short id shown in CLI |
| key | TEXT UNIQUE NOT NULL | `UID` for single events, `UID|original_start_utc` for recurring instances (R2). This is the deduplication key (FR-007). |
| ical_uid | TEXT NOT NULL | |
| original_start_utc | TEXT NULL | NULL for non-recurring events |
| title | TEXT NOT NULL | ≤ 100 chars after mapping |
| description | TEXT NOT NULL | ≤ 5000 bytes, no `<` `>` |
| start_utc | TEXT NOT NULL | Desired start (may differ from original if moved) |
| end_utc | TEXT NOT NULL | > start_utc |
| source_tz | TEXT NOT NULL | IANA zone from TZID, or `defaults.timezone` for floating times |
| visibility | TEXT NOT NULL | `public` \| `unlisted` \| `private` |
| desired_hash | TEXT NOT NULL | Hash of (title, description, start, end, visibility) |
| state | TEXT NOT NULL | See state machine below (includes `exists_external` from 004) |
| state_reason | TEXT NULL | Plain language. Set for failed, conflict, pending-deferred, owner_* states. |
| deferred_reason | TEXT NULL | `quota` \| `transient` \| NULL |
| attempts | INTEGER NOT NULL DEFAULT 0 | |
| intent_at | TEXT NULL | Set when entering `creating` (R5) |
| local_override | TEXT NULL | `skip` \| `approve_overlap` \| NULL (set via CLI) |
| first_seen_run_id / last_seen_run_id | INTEGER FK → run | |
| updated_at | TEXT NOT NULL | |

**Validation**:
- `start_utc` must be ≥ `now + safety.min_lead_minutes` (default 15) when created. Earlier instances are ignored, which covers past times in the edge cases.
- Duration must be between 1 minute and 12 hours, otherwise the occurrence is `failed`.
- All-day events are never turned into occurrences (R3).

### Occurrence state machine

```text
                    ┌────────────── retry next run ──────────────┐
                    ▼                                            │
 (new in window) → pending ──insert intent──► creating ──ok──► scheduled
                    │  ▲                         │                │  ▲
       overlap ─────┘  │ quota/transient         │ crash          │  │ desired changed → update ok
       → conflict      └─────────────────────────┘ (recovered R5) │  │
                                                                  │──┘
 pending/scheduled ── local skip ─────────────────────────► skipped   (broadcast deleted if any)
 pending/scheduled ── gone from feed ─────────────────────► cancelled (broadcast deleted if any)
 scheduled ── remote edited (hash ≠ last_written) ─────────► owner_modified (unmanaged)
 scheduled ── remote missing ──────────────────────────────► owner_deleted  (never recreated)
 pending/creating ── permanent error ──────────────────────► failed
 scheduled ── start passed or lifeCycleStatus ∉ {created,ready} ► past
 owner_modified/owner_deleted ── `occurrence reclaim` ──────► scheduled / pending
 conflict ── `occurrence approve` or overlaps: allow ───────► pending
 failed ── desired_hash changes or `occurrence retry` ──────► pending
```

Added by 004 (FR-010, research S6): `pending ── a hand-made livestream within ±15 min ──► exists_external`. It is never modified, and it goes back to `pending` if that livestream disappears. See [004 data-model](../004-taize-funeral-services/data-model.md).

Terminal states are `cancelled`, `skipped` and `past`. A `cancelled` occurrence whose key reappears in the feed (the owner restored the event) goes back to `pending`.

## broadcast

Records broadcasts this app created. A row's presence is the proof of ownership (FR-009, R5).

| Field | Type | Rules |
|---|---|---|
| broadcast_id | TEXT PK | YouTube `liveBroadcast.id` |
| occurrence_id | INTEGER UNIQUE FK → occurrence | At most one live mapping per occurrence |
| channel_id | TEXT NOT NULL | Must equal `channel_connection.channel_id` before any write |
| created_at | TEXT NOT NULL | |
| last_written_hash | TEXT NOT NULL | Hash of managed fields as we last wrote them (R6) |
| last_written_at | TEXT NOT NULL | |
| last_seen_remote_hash | TEXT NULL | Hash from latest `list` |
| life_cycle_status | TEXT NULL | Last observed (`created`, `ready`, `live`, `complete`, …) |
| bound_stream_id | TEXT NULL | If `youtube.stream_id` configured |
| deleted_at | TEXT NULL | Set when *we* deleted it. The row is kept for audit. |

**Rule**: every `update`/`delete` call's target id MUST come from this table where `deleted_at IS NULL`. There is no code path that writes to ids obtained from a channel listing. The only exception is R5 recovery, which inserts the adopted id here first.

## run

One row per `sync` invocation, covering FR-011 and SC-007.

| Field | Type | Rules |
|---|---|---|
| id | INTEGER PK | |
| started_at / finished_at | TEXT | |
| trigger | TEXT | `timer` \| `manual` (`--trigger` flag. Defaults to `timer` when `$INVOCATION_ID` is set by systemd, otherwise `manual`.) |
| outcome | TEXT | `success` \| `partial` (some deferred/failed) \| `failed` (aborted) \| `skipped_locked` |
| created / updated / removed / skipped / deferred / failed | INTEGER | Counters |
| error_class | TEXT NULL | `auth` \| `quota` \| `feed` \| `not_eligible` \| `safety_hold` \| `internal` |
| error_message | TEXT NULL | Plain language, no secrets (FR-015) |
| quota_units_est | INTEGER | Sum of estimated unit cost |
| config_commit | TEXT NULL | Short SHA of the config repo checkout active for this run (research R17); NULL if not a git checkout |

## run_item

One row per action attempted or decided in a run.

| Field | Type | Rules |
|---|---|---|
| id | INTEGER PK | |
| run_id | INTEGER FK → run | |
| occurrence_id | INTEGER FK NULL | |
| action | TEXT | `create` \| `update` \| `delete` \| `adopt` \| `skip` \| `defer` \| `conflict` \| `mark_owner_modified` \| `mark_owner_deleted` \| `fail` \| `external_conflict` (001/004 S6). Later features add `lectionary_pending`, `lectionary_invalid` (003) and `announce` (004). Backup runs use `backup` (R18). Stored as TEXT with no CHECK constraint, so features can extend it. |
| broadcast_id | TEXT NULL | |
| result | TEXT | `ok` \| `deferred` \| `error` |
| message | TEXT NULL | Plain language |

## notification

Holds email deduplication state (R10).

| Field | Type | Rules |
|---|---|---|
| problem_key | TEXT PK | e.g. `auth`, `feed`, `quota`, `safety_hold`, `occurrence:<id>:failed` |
| opened_at | TEXT | First detection |
| last_sent_at | TEXT | Re-send only if > 24 h ago |
| resolved_at | TEXT NULL | Set when the condition clears. Sends a single "resolved" email. |

## Backups (research R18)

Backups are archives, not tables. Each run of `backup` writes a run-log line (`run.trigger = timer|manual`, a `run_item` with `action = backup`, `message = <path> (<size>)`). A failure raises notification `problem_key = backup`. `restore` checks `schema_version` (from the `schema_version` table) against the archive manifest.

## Retention

`run` and `run_item` rows older than `retention_days` (default 90) are pruned at the end of each run. Occurrences in terminal states older than 90 days are pruned along with their `broadcast` rows where `deleted_at` is set or the start has passed.
