---
description: "Task list for 001 YouTube Livestream Scheduler (MVP)"
---

# Tasks: YouTube Livestream Scheduler (001)

**Input**: Design documents from `specs/001-youtube-livestream-scheduler/` (plan.md, spec.md, research.md R1–R16, data-model.md, contracts/, quickstart.md)

**Prerequisites**: none. This is the first feature built.

**Build order across features**: **001 (this file)** → [002](../002-description-templates/tasks.md) → [003](../003-lectionary-service-metadata/tasks.md) → [004](../004-taize-funeral-services/tasks.md). Task IDs restart in each file. Cross-file references look like `001:T012`.

**Tests**: INCLUDED. Every plan's baseline is test-first, and the plans name specific contract, golden and integration tests. Write each test task first and make sure it fails before implementing.

**Commits**: Conventional Commits, one per task or small group (e.g. `feat(sync): plan creates for new occurrences`). Run everything through uv: `uv run pytest`, `uv run ruff check`, `uv run mypy src`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1/US2/US3 from `specs/001-youtube-livestream-scheduler/spec.md`

---

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Create `pyproject.toml`:
  - build backend `hatchling`, `requires-python = ">=3.12,<3.13"`, console script `livestream-scheduler = "livestream_scheduler.cli:main"`
  - dependencies `google-api-python-client`, `google-auth`, `google-auth-oauthlib`, `icalendar>=6,<7`, `recurring-ical-events>=3,<4`, `click`, `pydantic>=2,<3`, `PyYAML`, `requests`, `platformdirs`
  - `[dependency-groups] dev = ["pytest", "time-machine", "responses", "ruff", "mypy", "types-PyYAML", "types-requests"]`
- [X] T002 [P] Run `uv lock` and commit `uv.lock` at the repo root (research R16). Pin Python only through `requires-python` in `pyproject.toml`. **Do not create `.python-version`**: dotfiles are never tracked in this repo.
- [X] T003 [P] Configure ruff (`[tool.ruff]`, target py312, line-length 100) and mypy (`strict = true`, `files = ["src"]`) in `pyproject.toml`. Add a tracked `.gitignore`, the **one** permitted dotfile (owner, 2026-10-08): `!/.gitignore` first (it overrides the `.*` rule in `.git/info/exclude`), then `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `dist/`, `build/`, `*.egg-info/`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `dev/`, `.DS_Store`, `*.tmp`, `*.swp`, `.vscode/`, `.idea/`.
- [X] T004 [P] Create the package skeleton `src/livestream_scheduler/__init__.py` (`__version__`), the empty subpackages `calendar/`, `youtube/`, `sync/`, `db/`, `db/schema/`, the test dirs `tests/unit/`, `tests/contract/`, `tests/integration/`, `tests/live/`, `tests/fixtures/ics/`, and `tests/conftest.py` with a `tmp_state_dir` fixture
- [X] T005 [P] Add `scripts/check.sh` (bash, `set -euo pipefail`): `uv sync --locked && uv run ruff check && uv run mypy src && uv run pytest -m "not live"`, with `--fast` skipping integration tests. Add `scripts/install-git-hooks.sh`, which writes an **untracked** `.git/hooks/pre-commit` that runs `scripts/check.sh --fast`. These replace hosted CI, which would need the `.github/` dotfolder (owner rule: no tracked dotfiles).

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Tests first

- [X] T006 [P] Write `tests/unit/test_paths.py` for the resolution order in contracts/deployment.md:
  - config: `--config` → `$LSS_CONFIG` → `$CONFIGURATION_DIRECTORY/config.yaml` → platformdirs
  - state: `--state-dir` → `$LSS_STATE_DIR` → `$STATE_DIRECTORY` → platformdirs
- [X] T007 [P] Write `tests/unit/test_secrets.py`:
  - `{credential: name}` reads `$CREDENTIALS_DIRECTORY/name`
  - `{env: VAR}` reads the env var
  - `{file: path}` rejects modes wider than 0600 (0400 is accepted)
  - a missing credential raises the message `credential "calendar-url" not found in $CREDENTIALS_DIRECTORY (is LoadCredential= set?)`
- [X] T008 [P] Write `tests/unit/test_logging_redaction.py`: `ya29.` tokens, `refresh_token`, `client_secret`, `Authorization:` headers and ICS URLs containing `/ical/` are redacted. In journald mode (`$JOURNAL_STREAM` set) there are no timestamps.
- [X] T009 [P] Write `tests/unit/test_config.py` covering every validation row in contracts/config-schema.md:
  - exactly one of `calendar.url` / `calendar.path`
  - unknown keys → error
  - `defaults.timezone` must be a valid IANA zone
  - `visibility ∈ {public, unlisted, private}`
  - `horizon.days` in 1..180
  - `youtube.channel_handle must look like @handle`
  - a plain-string `calendar.url` → warning

### Implementation

- [X] T010 [P] Implement `src/livestream_scheduler/paths.py` (resolution per T006; `ensure_private(path)` refuses to start if `token.json` is wider than 0600)
- [X] T011 [P] Implement `src/livestream_scheduler/secrets.py`: a `SecretRef` union (`credential` | `env` | `file` | plain str with warning) and `resolve()`
- [X] T012 [P] Implement `src/livestream_scheduler/logging.py`: stderr handler, a `RedactingFilter`, and journald-aware formatting when `$JOURNAL_STREAM` is set
- [X] T013 Implement `src/livestream_scheduler/config.py`: pydantic v2 models for the whole YAML in contracts/config-schema.md (`version`, `google`, `calendar`, `defaults`, `youtube.channel_handle` (required, starts with `@`), `youtube.channel_id` (optional), `youtube.stream_id`, `horizon.days` (default 28), `overlaps` (`warn`|`allow`), `safety.min_lead_minutes` (default 15), `safety.max_removals_per_run` (default 5), `notify.*` with secret refs, `retention_days` (default 90), **`google.client_secret` as a secret ref** (default `{credential: oauth-client}`; research R19), **`backup.dir` (absolute, default `/var/backups/livestream-scheduler`), `backup.keep` (≥1, default 14), `backup.passphrase` (optional secret ref)**) with `extra="forbid"`. Depends on T011.
- [X] T014 Write `src/livestream_scheduler/db/schema/0001_init.sql` with every table in data-model.md:
  - `channel_connection` with `CHECK (id = 1)`, `channel_handle TEXT NOT NULL`, status in (`connected`,`needs_reauth`,`not_eligible`)
  - `calendar_source` with `CHECK (id = 1)`; `url_hash` holds the SHA-256 only, never the URL
  - `occurrence`:
    - `key TEXT UNIQUE NOT NULL`, `original_start_utc TEXT NULL`
    - `state` covering `pending, creating, scheduled, skipped, cancelled, failed, conflict, owner_modified, owner_deleted, past, exists_external`
    - `deferred_reason` in (`quota`,`transient`,NULL), `local_override` in (`skip`,`approve_overlap`,NULL)
    - **plus the 004 S6 columns `external_broadcast_id`, `external_title`, `external_start_utc` (TEXT NULL)**
  - `broadcast` with `occurrence_id INTEGER UNIQUE`, `deleted_at TEXT NULL`
  - `run` with `outcome` in (`success`,`partial`,`failed`,`skipped_locked`), `trigger` in (`timer`,`manual`), `dry_run INTEGER`, `config_commit TEXT NULL`
  - `run_item`
  - `notification` with `problem_key TEXT PK`
- [X] T015 Implement `src/livestream_scheduler/db/migrate.py`: `schema_version` table, forward-only application of `db/schema/*.sql` in order, `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`. Depends on T014.
- [X] T016 Implement `src/livestream_scheduler/db/repo.py`: typed dataclasses and accessors for every table, with all writes inside explicit transactions. Depends on T015.
- [X] T017 [P] Implement `src/livestream_scheduler/lock.py`: a non-blocking exclusive `fcntl.flock` on `<state_dir>/state.lock`, plus a `LockHeld` exception
- [X] T018 [P] Implement `src/livestream_scheduler/youtube/port.py` per contracts/youtube-port.md:
  - the `YouTubePort` Protocol: `whoami`, `get_broadcasts`, `list_upcoming`, `insert_broadcast`, `update_broadcast`, `delete_broadcast`, `bind`
  - the dataclasses `Channel(id, title, handle)`, `BroadcastSpec`, `Broadcast` with `managed_hash()` (UTC second precision, newline-normalized)
  - the exceptions `AuthError`, `ChannelMismatch`, `NotEligible`, `QuotaExceeded`, `TransientError`, `BroadcastNotFound`, `InvalidRequest(reason, message)`
- [X] T019 [P] Implement `src/livestream_scheduler/youtube/fake.py`: an in-memory `FakeYouTube`. It can pre-seed broadcasts "created by hand" (not via insert), inject errors per call, count quota per the contract table, and fail with `QuotaExceeded` after N writes.
- [X] T020 Write `tests/contract/test_youtube_port.py`: invariants 1–6 of contracts/youtube-port.md, parametrized over adapters (FakeYouTube now; GoogleYouTube added in T031). Depends on T018, T019.
- [X] T021 Implement the CLI skeleton in `src/livestream_scheduler/cli.py`:
  - a click group with the global options `--config`, `--state-dir`, `--json`, `-v/-q`
  - an `ExitCode` IntEnum (0, 1, 2, 3, 4, 5, 10) and a `main()` that maps exceptions to exit codes

**Checkpoint**: `uv run pytest tests/unit tests/contract` passes. The foundation is ready.

---

## Phase 3: User Story 1 - Connect a channel and auto-schedule upcoming livestreams (Priority: P1) 🎯 MVP

**Goal**: Connect @minnehahaumc once. Every calendar occurrence in the 4-week horizon then exists as an upcoming broadcast.

**Independent Test**: The weekly ICS fixture + FakeYouTube + `connect` (mocked flow) + `sync` → 4 broadcasts with the correct title, start (America/Chicago → UTC), end and privacy. `sync` without a connection → exit 3 and 0 API calls.

### Tests for User Story 1 ⚠️

- [X] T022 [P] [US1] Add ICS fixtures under `tests/fixtures/ics/`:
  - `weekly.ics` (Tuesday 19:00 America/Chicago, RRULE weekly)
  - `overrides.ics` (a RECURRENCE-ID moved instance)
  - `exdate.ics`
  - `dst.ics` (instances across 2026-11-01 and 2027-03-14)
  - `allday.ics`
  - `html-desc.ics` (an HTML DESCRIPTION with `yt.visibility: unlisted`)
  - `floating.ics` (no TZID)
  - `empty.ics`
- [X] T023 [P] [US1] Write `tests/unit/calendar/test_expand.py`:
  - keys are `UID` for single events and `UID|YYYY-MM-DDTHH:MM:SSZ` (original start) for recurring instances
  - EXDATE is excluded
  - a moved instance keeps its key
  - 19:00 local is kept across DST (UTC differs by 1 h)
  - instances before `now + min_lead_minutes` are excluded
  - the window ends at `now + horizon.days`
- [X] T024 [P] [US1] Write `tests/unit/calendar/test_mapping.py` covering every row in contracts/calendar-mapping.md:
  - the title is truncated to 100 chars with a warning; an empty title gives `failed: "Event has no title"`
  - HTML is converted to text and directive lines are removed
  - `<` `>` are stripped and the description is capped at 5000 UTF-8 bytes
  - a missing DTEND means DTSTART + 1 h
  - `yt.visibility` overrides `defaults.visibility`
  - an unknown `yt.*` directive gives a warning
  - all-day events are skipped
  - the `include.summary_prefix` filter strips the prefix
- [X] T025 [P] [US1] Write `tests/unit/test_auth.py`:
  - `connect` stores `token.json` with mode 0600
  - the handle check is case-insensitive
  - another channel → revoke + exit 3 with `Authorized channel "<title>" (@<handle>) is not @minnehahaumc; …`
  - a `youtube.channel_id` mismatch is rejected
  - `disconnect` POSTs to the revoke URL and deletes the file
- [X] T026 [P] [US1] Write `tests/integration/test_us1_acceptance.py`: US1-1 (4 broadcasts created and fields match), US1-2 (not connected → exit 3, no API calls), US1-3 (wrong channel refused, then the right channel is accepted)

### Implementation for User Story 1

- [X] T027 [P] [US1] Implement `src/livestream_scheduler/calendar/fetch.py`: an HTTPS GET of the resolved secret URL with `If-None-Match`/`If-Modified-Since` and a 15 s timeout, or a local `path`. It stores `etag`/`last_modified`/`url_hash`/`last_body_sha256` in `calendar_source`, and never logs the URL.
- [X] T028 [P] [US1] Implement `src/livestream_scheduler/calendar/expand.py`: `icalendar` + `recurring-ical-events` over `[now+min_lead, now+horizon]` producing the key rule above. Floating times use `defaults.timezone`; `STATUS:CANCELLED` instances are excluded.
- [X] T029 [P] [US1] Implement `src/livestream_scheduler/calendar/mapping.py`: `DesiredOccurrence` (key, title, description, start_utc, end_utc, source_tz, visibility, directives dict, warnings) per contracts/calendar-mapping.md, including directive parsing (`yt.<name>: <value>`, case-insensitive), the **`calendar.include` filter** (`summary_prefix`: keep only matching titles and strip the prefix; `directive: true`: keep only events with `yt.stream: yes`), and `desired_hash`
- [X] T030 [US1] Implement `src/livestream_scheduler/auth.py`:
  - `InstalledAppFlow.from_client_config(json.loads(resolve(config.google.client_secret)))` (research R19; never a plain file path in production) with the loopback redirect, `--no-browser`, and `--port` (fixed when no-browser)
  - scope `https://www.googleapis.com/auth/youtube.force-ssl`
  - token saved to `<state_dir>/token.json` with mode 0600
  - `whoami()` check against `youtube.channel_handle` (and `channel_id` if set), then the `channel_connection` row is written
  - revoke on `disconnect` via `https://oauth2.googleapis.com/revoke`

  Depends on T010, T016.
- [X] T031 [US1] Implement `src/livestream_scheduler/youtube/google_adapter.py`:
  - `GoogleYouTube` implementing the port, with read-merge-write `update` and batched `get_broadcasts` (≤50 ids)
  - the error mapping table from contracts/youtube-port.md
  - 3 in-call retries with exponential backoff and jitter for `TransientError`
  - quota unit accounting (list 1, write 50)
  - add GoogleYouTube to T020's parametrization using `googleapiclient.http.HttpMockSequence` fixtures in `tests/fixtures/google/`
- [X] T032 [US1] Implement the create path of `src/livestream_scheduler/sync/planner.py`: a pure `plan(desired, recorded, now, config) -> list[Action]`. New keys → `Create`, ordered by ascending start. Overlapping `[start, end)` → the later one becomes `Conflict` unless `overlaps: allow`, `yt.allow-overlap: yes`, or `local_override=approve_overlap`.
- [X] T033 [US1] Implement the create handling of `src/livestream_scheduler/sync/executor.py`:
  - commit the occurrence as `creating` with `intent_at`, then call `insert_broadcast`
  - write the `broadcast` row (`last_written_hash`) and set state `scheduled`
  - call `bind` if `youtube.stream_id` is set
  - map exceptions per research R8 (`QuotaExceeded` stops writes and defers the rest; `NotEligible` aborts with connection → `not_eligible`; `AuthError` aborts with connection → `needs_reauth`)
- [X] T034 [US1] Implement `src/livestream_scheduler/sync/run.py`: acquire the lock (`LockHeld` → exit 0, outcome `skipped_locked`), create the `run` row (trigger = `--trigger` or `timer` if `$INVOCATION_ID` else `manual`), verify the connection and channel, then fetch → expand → map → plan → execute, then finalize counts and outcome.
  - **`--dry-run`**: run everything through planning, print the planned actions, make **no** YouTube writes and **no** changes to `occurrence`/`broadcast`/`calendar_source`, and write a `run` row with `dry_run=1` and the counters the plan would produce (contracts/cli.md)
- [X] T035 [US1] Add the CLI commands `connect [--no-browser] [--port N] [--forget-tracked]`, `disconnect`, `sync [--dry-run] [--allow-mass-removal] [--trigger timer|manual]`, `status` and `config check` to `src/livestream_scheduler/cli.py`, with the human output formats in contracts/cli.md
- [X] T036 [US1] Add `examples/config.yaml`, the full production example from contracts/config-schema.md (Minnehaha values: `channel_handle: "@minnehahaumc"`, `channel_id: UCzwZQ34D3RZEncTf6fAe0hQ`, `timezone: America/Chicago`, `{credential: …}` secret refs, `client_secrets_file: /etc/livestream-scheduler/client_secret.json`), and `examples/dev-config.yaml` for local development (the same values with `{env: LSS_CALENDAR_URL}` / `{env: LSS_SMTP_PASSWORD}` and `client_secrets_file: ./dev/client_secret.json`), as used in quickstart.md "Local development". (`dev/` is ignored by `.gitignore`.) Also add **`examples/config-repo/`**, the seed for the owner's separate config repository (research R17):
  - `config.yaml` (the production example)
  - `templates/README.md` (a placeholder explaining overrides; no `.gitkeep`, since dotfiles aren't tracked)
  - `README.md` (layout; deploy with `install.sh config-pull`; never commit secrets)
  - `gitignore.example` (`credentials/`, `client_secret*.json`, `token*.json`, `*.age`, `backups/`), which the owner may install as the config repo's ignore list. The secret-scan guard (T060) is the enforcement.

**Checkpoint**: US1 integration tests pass. A dry run against a real test channel shows the expected creates.

---

## Phase 4: User Story 2 - Keep the schedule in sync without duplicates (Priority: P2)

**Goal**: Repeated runs are idempotent. Calendar changes become updates or removals. Broadcasts created by hand are never touched, and they are not duplicated (004 S6, required before the first live run).

**Independent Test**: 30 consecutive syncs with no changes → 0 API writes. Rename, move or delete in the fixture → update or delete only for owned broadcasts. A hand-made broadcast at the same time → `exists_external` and no insert.

### Tests for User Story 2 ⚠️

- [X] T037 [P] [US2] Write `tests/unit/sync/test_planner_updates.py`:
  - a changed `desired_hash` → `Update`
  - a key gone from the feed → `Delete` (state `cancelled`)
  - `local_override=skip` → `Delete` + `skipped`
  - a key that reappears after `cancelled` → `pending`
  - past starts → `past`
  - order: deletes, then updates, then creates
- [X] T038 [P] [US2] Write `tests/unit/sync/test_safety.py` (research R7):
  - a feed fetch or parse failure → no deletes planned
  - removals > `max_removals_per_run` (5), or all active removed → `SafetyHold` (exit 5) unless `allow_mass_removal`
- [X] T039 [P] [US2] Write `tests/integration/test_us2_acceptance.py` (and the catch-up test below):
  - US2-1: 30 consecutive runs produce 0 duplicates and 0 writes (SC-003)
  - US2-2: a rename or time change updates the same video id
  - US2-3: an instance deleted from the calendar → its broadcast deleted
  - US2-4: a broadcast created by hand is never modified
  - **catch-up after downtime** (spec edge case): sync at day 0, advance time-machine by 5 days with no runs, sync once → exactly the occurrences that entered the horizon are created, 0 duplicates, past ones become `past`
  - **dry run**: `sync --dry-run` → 0 API writes, 0 occurrence or broadcast changes, and one `run` row with `dry_run=1` and counters equal to what a real run then produces
- [X] T040 [P] [US2] Write `tests/integration/test_manual_changes.py` (research R6):
  - a remote title edited → `owner_modified`, not overwritten
  - a remote broadcast deleted → `owner_deleted`, never recreated
  - `lifeCycleStatus=live` → `past`, untouched
  - `occurrence reclaim` restores management
- [X] T041 [P] [US2] Write `tests/integration/test_crash_recovery.py` (research R5):
  - a crash after insert and before commit → the next run adopts the broadcast whose `publishedAt ≥ intent_at − 2 min` with an exact title and start match
  - two matches → `failed` with `ambiguous_recovery`
  - no match → insert retried
- [X] T042 [P] [US2] Write `tests/integration/test_external_conflict.py` (001 FR-017 / US2-5, which is 004 FR-010 and research S6):
  - FakeYouTube is pre-seeded with a broadcast created by hand at `2026-10-10T00:00:00Z` titled `October 9th, 2026 - Taizé`, and the calendar has Friday 2026-10-09 19:00 America/Chicago
  - expected: occurrence `exists_external` with `external_broadcast_id` set, 0 inserts, and 0 updates or deletes on that id
  - after the fake removes it, the next run creates our own
  - a ±16 min offset does **not** block
- [X] T043 [P] [US2] Write `tests/integration/test_quota_and_transient.py`:
  - `QuotaExceeded` after 2 inserts → the rest stay `pending` with `deferred_reason=quota`, run `partial` (exit 1), and the next run completes them with no duplicates
  - 5xx ×3 → `deferred_reason=transient`

### Implementation for User Story 2

- [X] T044 [US2] Extend `src/livestream_scheduler/sync/planner.py` with the update, delete, skip, cancel and past transitions and the R7 safety hold. The data-model.md state machine is the specification; implement every arrow. Depends on T032.
- [X] T045 [US2] Implement the manual-change detection (R6) in `src/livestream_scheduler/sync/executor.py`:
  - before any update or delete, `get_broadcasts` the owned ids (batched)
  - missing → `owner_deleted`
  - `managed_hash() != last_written_hash` → `owner_modified`
  - `life_cycle_status ∉ {created, ready}` → `past`
  - every update or delete target id MUST come from the `broadcast` table with `deleted_at IS NULL`
- [X] T046 [US2] Implement `src/livestream_scheduler/sync/recovery.py` (R5): recover `creating` occurrences via `list_upcoming(since=intent_at)` under the adoption rules in T041. Wire it into `run.py` before planning.
- [X] T047 [US2] Implement `src/livestream_scheduler/sync/external.py` (001 FR-017, 004 S6):
  - when the plan has ≥1 `Create` or any `exists_external` rows exist, call `list_upcoming(since=None)` once (the contract default means "from now")
  - mark pending occurrences with an unowned broadcast within ±15 min as `exists_external` (store id, title, start), removing their `Create`
  - put `exists_external` back to `pending` when the external broadcast is gone and the start is in the future; set it to `past` once the start has passed
  - wire into `run.py` between plan and execute
- [X] T048 [US2] Implement quota and transient deferral bookkeeping in `src/livestream_scheduler/sync/executor.py` (`deferred_reason`, `attempts`, run outcome `partial`) and the `run_item` rows for every action (`create`, `update`, `delete`, `adopt`, `skip`, `defer`, `conflict`, `mark_owner_modified`, `mark_owner_deleted`, `fail`, `external_conflict`)
- [X] T049 [US2] Add the CLI commands `occurrence skip|unskip|approve|reclaim|retry <id>` to `src/livestream_scheduler/cli.py` (contracts/cli.md)

**Checkpoint**: US1 and US2 tests pass. It is safe to run against the live channel: hand-made broadcasts like the Oct 9 Taizé are protected.

---

## Phase 5: User Story 3 - See what was scheduled and what failed (Priority: P3)

**Goal**: The run history, the occurrence list and email notifications on state changes.

**Independent Test**: One valid and one failing occurrence → `runs --run <id>` shows both with plain-language messages. One email per problem transition, with 24 h reminders, then a "resolved" email.

### Tests for User Story 3 ⚠️

- [X] T050 [P] [US3] Write `tests/unit/test_notify.py` (research R10):
  - one email on success→failure, on `needs_reauth`, on a safety hold and on a conflict
  - no repeat within `reminder_hours` (24); a reminder after it
  - one "RESOLVED" email when the problem clears
  - no tokens, secrets or ICS URL in any email body
- [X] T051 [P] [US3] Write `tests/integration/test_us3_acceptance.py`: US3-1 (`runs`, `runs --run` show time, counts and items; the `--json` shapes match contracts/cli.md) and US3-2 (revoked auth → exit 3, an email with "reconnect needed", no changes)

### Implementation for User Story 3

- [X] T052 [P] [US3] Implement `src/livestream_scheduler/notify.py`: SMTP (`starttls`|`ssl`|`none`) with the password from a secret ref, the subject format `[livestream-scheduler] <PROBLEM|RESOLVED>: <short reason>`, and deduplication through the `notification` table (`opened_at`, `last_sent_at`, `resolved_at`)
- [X] T053 [US3] Wire notifications into `src/livestream_scheduler/sync/run.py` at the end of each run, covering all R10 transitions and `external:<occurrence_id>` (one-shot "Already on the channel" notice per 004 contracts/cli-additions.md)
- [X] T054 [US3] Add the CLI commands `runs [--limit N] [--run ID]`, `occurrences [--state …] [--all]` and `notify test` to `src/livestream_scheduler/cli.py`, with the `--json` shapes from contracts/cli.md
- [X] T055 [US3] Implement retention pruning in `src/livestream_scheduler/sync/run.py`: delete `run`/`run_item` older than `retention_days` (90) and terminal occurrences older than 90 days

**Checkpoint**: All 001 user stories pass independently.

---

## Phase 6: User Story 4 - Back up, restore, and move the installation (Priority: P3)

**Goal**: Config lives in a separate git repo with no secrets. Daily backups exclude secrets. A restore on a new server keeps every recorded livestream managed.

**Independent Test**: Sync with FakeYouTube (3 broadcasts created) → `backup` → restore into a fresh state dir → sync: 0 creates, a calendar rename updates the same 3 ids. The default archive contains no secrets.

### Tests for User Story 4 ⚠️

- [X] T056 [P] [US4] Write `tests/unit/test_secretscan.py` (research R17, FR-022, SC-009). A config dir containing any of these fails `config check`:
  - `credentials/`, `client_secret.json`, `token.json`, `x.age`
  - a YAML value matching `/ical/`, `private-`, `ya29.` or `GOCSPX-`

  A clean seed from `examples/config-repo/` passes.
- [X] T057 [P] [US4] Write `tests/integration/test_backup.py` (FR-019, FR-020):
  - the archive holds exactly `manifest.json`, `state.db` and `config/**`; the manifest has the app version, `schema_version`, channel id and handle, `config_commit`, per-file SHA-256 and `secrets_included=false`
  - the snapshot is consistent while a second connection writes (SQLite online backup)
  - `--prune` keeps the newest `backup.keep`
  - grepping the default archive for `ya29.`, `refresh_token`, `GOCSPX-`, `client_secret` and the fixture ICS URL finds nothing
  - `--include-secrets` without `age` on PATH → exit 2
- [X] T058 [P] [US4] Write `tests/integration/test_restore.py` (FR-021, US4-1..3):
  - restore into a fresh state dir, then sync → 0 inserts, and a calendar rename updates the restored broadcast ids
  - refuse (exit 2, nothing written) on: manifest `schema_version` > installed, newer app version, channel id mismatch, and an existing `state.db` with a newer run unless `--force`
  - with `--include-secrets` (skipped if `age` is not installed): `token.json` restored with mode 0600, no `connect` needed; a wrong passphrase → nothing written
  - restored `config/` is not applied unless `--apply-config`
- [X] T059 [P] [US4] Write `tests/integration/test_unmanaged_report.py` (spec edge cases): an empty `state.db` while FakeYouTube has 3 upcoming broadcasts created by the app → `status` reports `3 upcoming livestreams on the channel are not managed (no record)`. Sync creates none (FR-017 guard) and sends one notification.

### Implementation for User Story 4

- [X] T060 [P] [US4] Implement `src/livestream_scheduler/secretscan.py` with the R17 file patterns and value regexes. Call it from `config check` (and from `templates check` for the templates dir) in `src/livestream_scheduler/cli.py`.
- [X] T061 [US4] Implement `backup()` in `src/livestream_scheduler/backup.py` (research R18):
  - take the lock (non-blocking; on `LockHeld` retry for up to 10 min)
  - `sqlite3` online backup into a temp dir; copy the active config dir (excluding `.git/`)
  - write `manifest.json`; tar.gz to `lss-backup-<UTC>-v<version>.tar.gz`
  - with `include_secrets`: add `token.json` + `$CREDENTIALS_DIRECTORY/*`, then encrypt via `age -p` (passphrase typed at the terminal; `age` has no non-interactive passphrase input, so `backup.passphrase` is rejected), giving `.tar.gz.age`; delete the plaintext
  - prune
  - record a `run` + `run_item(action=backup)`; on failure notify `problem_key=backup`
- [X] T062 [US4] Implement `restore()` in `src/livestream_scheduler/backup.py` per R18 steps 1–7:
  - decrypt to a temp dir (0700), verify checksums, run the version, channel and newer-state checks
  - place `state.db` (and `token.json`) with mode 0600, owned by the running user
  - run `migrate.py`
  - report the missing credentials and whether `connect` is needed
  - never call YouTube
- [X] T063 [US4] Add the CLI commands `backup [--output DIR] [--include-secrets] [--prune]` and `restore PATH [--force] [--apply-config]` to `src/livestream_scheduler/cli.py`. Extend `status` with `config: <repo> @ <sha>` (record `run.config_commit` in `sync/run.py` by reading `<config dir>/.git/HEAD` without invoking git), the last backup time, and the unmanaged upcoming count (from the latest `list_upcoming` vs `broadcast`).
- [X] T064 [P] [US4] Add `deploy/systemd/livestream-scheduler-backup.service` and `livestream-scheduler-backup.timer`, verbatim per contracts/deployment.md (`OnCalendar=daily`, `RandomizedDelaySec=30min`, `Persistent=true`, `ReadWritePaths=/var/backups/livestream-scheduler`, only `LoadCredential=oauth-client`, `ExecStart=… backup --output /var/backups/livestream-scheduler --prune`)

**Checkpoint**: All 001 user stories, including portability and recovery, pass independently.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T065 [P] Add `deploy/systemd/livestream-scheduler.service` and `deploy/systemd/livestream-scheduler.timer`, verbatim from contracts/deployment.md (hardening, `LoadCredential=`, `SuccessExitStatus=1`, `OnCalendar=hourly`, `Persistent=true`, `RandomizedDelaySec=5min`)
- [X] T066 [P] Add `deploy/lss`: a POSIX sh wrapper around `systemd-run --pty --wait --collect --uid=livestream-scheduler …` that runs `uv run --frozen --no-sync --project /opt/livestream-scheduler livestream-scheduler "$@"` (contracts/deployment.md). Mark it executable.
- [X] T067 Write `deploy/install.sh` (bash, `set -euo pipefail`, idempotent, run with sudo). Usage: `deploy/install.sh vX.Y.Z --config-repo <URL> [--config-ref main]`, plus the subcommands `config-pull [--ref <ref>]` and `restore <backup>` (contracts/deployment.md, research R17/R18):
  - check: Ubuntu (via `/etc/os-release`), `systemctl --version` ≥ 250 (abort on 22.04 with a clear message), `timedatectl show -p NTPSynchronized` = yes (warn otherwise)
  - `apt-get install -y git curl ca-certificates sqlite3 age`
  - create the `livestream-scheduler` system user and the directories with the owners and modes in contracts/deployment.md "Layout on the host"
  - install a pinned uv to `/usr/local/bin`; check out the tag to `/opt/livestream-scheduler`; `uv sync --frozen --no-dev --python 3.12` with `UV_PYTHON_INSTALL_DIR`
  - clone `--config-repo` to `/etc/livestream-scheduler` (root:livestream-scheduler, 0750) if absent
  - create `/etc/livestream-scheduler-credentials/` (root, 0700); prompt for any missing credential (the path of the downloaded OAuth client JSON → copy to `oauth-client.json`; `read -s` for `calendar-url` and `smtp-password`) and write each with mode 0600
  - `mkdir -p /var/backups/livestream-scheduler` (livestream-scheduler, 0700)
  - `config-pull`: fetch, check out `--ref` into a staging worktree, run `config check` + `templates check` as the service user against the staging dir via `lss --config <staging>/config.yaml`, then atomically switch `/etc/livestream-scheduler` to that commit only on success; otherwise exit 1 and leave the active commit unchanged
  - `restore <backup>`: run `lss restore <backup>` (prompts for the passphrase if `.age`), then place any restored credentials into `/etc/livestream-scheduler-credentials/` with mode 0600
  - install both unit pairs (sync + backup) and `lss`; `systemctl daemon-reload`; do **not** enable either timer
  - print next steps: copy `client_secret.json`, `lss config check`, the SSH tunnel + `lss connect --no-browser --port 8765`, `lss sync --dry-run`, `systemctl enable --now livestream-scheduler.timer livestream-scheduler-backup.timer`
  - target: under 10 minutes total with the `lss connect` step (SC-001)
- [X] T068 [P] Write `README.md` covering the purpose, local development with uv, home-server deployment on Ubuntu 24.04 via `deploy/install.sh` (pointing to the quickstart), a short "What is the Google Cloud project for?" note (free API registration only; nothing is hosted at Google), the **config repository workflow** (edit, push, `install.sh config-pull`), **backups and moving servers** (copy `/var/backups/livestream-scheduler` off the server; the steps in contracts/deployment.md "Move to a new server"), Conventional Commits, and the Google OAuth "In production" requirement (research R9)
- [X] T069 [P] Write `tests/live/test_smoke.py`, marked `live` and skipped unless `LSS_LIVE_TEST=1`: create, update and delete one broadcast on a test channel and clean up
- [ ] T070 Run `uv run ruff check`, `uv run mypy src` and `uv run pytest`. Then walk through quickstart.md manual scenarios 1–19 on the test channel and record the results in `specs/001-youtube-livestream-scheduler/quickstart.md` notes.
- [ ] T071 Run the FR-015 secret audit and record the result in `specs/001-youtube-livestream-scheduler/quickstart.md`: grep the journald output and a `state.db` dump for `ya29.`, `refresh_token`, `client_secret` and the ICS URL (quickstart #12). Expect 0 hits.

---

## Dependencies & Execution Order

- **Setup (T001–T005)** → **Foundational (T006–T021)** → **US1 (T022–T036)** → **US2 (T037–T049)** → **US3 (T050–T055)** → **US4 (T056–T064)** → **Polish (T065–T071)**.
- US2 depends on US1's planner and executor (T032–T034). US3 depends on `run.py` (T034), and its tests are independent of US2. US4 depends on Foundational (config, secrets, DB) and on `status` (T035); T058's restore-then-sync test also needs US2.
- T067 (`install.sh`) depends on T065, T066 and T064 (it installs all units and `lss`).
- **The live channel must not see a real `sync` until T047 (the hand-made broadcast guard) is done.**

## Parallel Opportunities

- Setup: T002–T005 together.
- Foundational tests T006–T009 together, then the implementations T010–T012, T017–T019 together.
- US1: T022–T026 (tests) together, then T027–T029 together.
- US2: T037–T043 (all tests) together.
- US4: T056–T059 (tests) together. T060 and T064 in parallel with T061–T063.
- Polish: T065, T066, T068 and T069 together (T067 after T064–T066).

## Implementation Strategy

1. **MVP = Phases 1–4 (US1 + US2)**. Creation alone (US1) is not safe for the live channel without idempotence and the hand-made broadcast guard.
2. Deploy to the server with the systemd timer **disabled**. Run `lss sync --dry-run`, then `lss sync`, then enable the timer.
3. Add US3 (visibility and notifications) and **US4 (backups; enable the backup timer as soon as the first real livestreams exist)**, then continue with [002 tasks](../002-description-templates/tasks.md).
