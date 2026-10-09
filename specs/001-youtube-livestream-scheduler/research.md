# Phase 0 Research: YouTube Livestream Scheduler

**Feature**: `001-youtube-livestream-scheduler` | **Date**: 2026-10-08

These decisions settle every open item in the plan's Technical Context. Owner decisions from the 2026-10-08 clarification: the schedule comes from an **external calendar**, the language is **Python**, and the app runs as a **CLI on cron with a YAML config**.

---

## R1. Calendar source format

- **Decision**: Read a single **iCalendar (ICS) feed URL** over HTTPS, such as Google Calendar's "secret address in iCal format", an Outlook published calendar, or a self-hosted `.ics` file. A local file path is also accepted, which is useful for tests and for owners who prefer files.
- **Rationale**: One format covers Google, Outlook, Apple and Proton calendars. It needs no second OAuth grant, and it avoids the case where the calendar's Google account differs from the YouTube brand account. ICS carries everything required: `UID`, `DTSTART`/`DTEND` with `TZID`, `RRULE`/`RDATE`/`EXDATE`, `RECURRENCE-ID` overrides, `SUMMARY`, and `DESCRIPTION`.
- **Alternatives considered**:
  - *Google Calendar API* (`events.list` with `singleEvents=true`): it expands recurrences server-side and has fresher data, but it locks the owner into Google and needs a second scope and possibly a second account. It can be added later as a second `CalendarSource` adapter.
  - *CalDAV*: more general, but it brings much more protocol surface for no gain in v1.
- **Known limitation**: Google refreshes its published ICS feeds with a lag that can reach several hours. That is acceptable under SC-004 (≤ 24 h) and is documented for the owner.

## R2. Recurrence expansion and occurrence identity

- **Decision**: Parse the feed with `icalendar` (6.x) and expand it with `recurring-ical-events` (3.x) over the window `[now + min_lead, now + horizon]`. The **occurrence key** for a recurring instance is `UID` + `|` + the instance's *original* start in UTC (from `RECURRENCE-ID` if present, otherwise the expanded `DTSTART`). A non-recurring event's key is its `UID` alone.
- **Rationale**: The original start stays fixed when one instance is moved, and a single event's `UID` stays fixed when it is moved, so a move counts as an *update*, not a delete plus create (FR-007, FR-008). `recurring-ical-events` correctly handles `EXDATE`, `RDATE`, overridden instances, and `TZID`-aware DST arithmetic (FR-014).
- **Alternatives considered**: Hand-rolled `dateutil.rrule` expansion was rejected because overrides, EXDATE and DST edge cases are where bugs hide. Keying on summary plus start was rejected because a rename would cause a duplicate.

## R3. Mapping calendar events to broadcasts

- **Decision**:
  - `SUMMARY` → title, truncated to YouTube's 100-character limit with a warning.
  - `DESCRIPTION` → description, with HTML stripped (Google exports HTML), `<`/`>` removed, and length capped at 5000 bytes.
  - `DTSTART`/`DTEND` → `scheduledStartTime`/`scheduledEndTime` in UTC.
  - Visibility comes from config `defaults.visibility`. A single event can override it with **directive lines** in its description, for example `yt.visibility: unlisted`. Directive lines are removed before publishing.
  - Events are included only if they match the optional `calendar.include` filter (summary prefix or a `yt.stream: yes` directive). The default is *all events*, so owners should use a dedicated calendar.
  - All-day events have no start time, so they are skipped with a warning.
- **Rationale**: Calendars cannot express YouTube-specific fields. Description directives work in every calendar client with no schema. The full contract is in [contracts/calendar-mapping.md](contracts/calendar-mapping.md).
- **Alternatives considered**: ICS `CLASS` for visibility was rejected because clients set it inconsistently. `CATEGORIES` was rejected because Google Calendar does not expose it.

## R4. YouTube API usage

- **Decision**: Use `google-api-python-client` against YouTube Data API v3 `liveBroadcasts`:
  - `insert` with `part=snippet,status,contentDetails`
  - `update` with the same parts. This is a full replace of those parts, so the client reads the broadcast first and writes back the merged result.
  - `delete`
  - `list` by `id` (batched up to 50 ids, 1 quota unit)
  - `channels.list(mine=true)` to identify the channel
  - Optional: `liveBroadcasts.bind` to a configured reusable `liveStreams` id, so every broadcast uses the owner's existing stream key.
- **Quota**: The default budget is 10,000 units per day. Writes (`insert`/`update`/`delete`/`bind`) cost about 50 units each, and `list` costs 1. A 4-week horizon of 3 streams a week needs about 12 inserts at first (~600 units) and almost nothing per hourly run afterwards. Separately from units, YouTube enforces an **undocumented per-day limit on broadcast creation**. That limit is treated the same as `quotaExceeded` (R8).
- **Rationale**: This is the only official API for scheduling broadcasts. The full contract and error mapping are in [contracts/youtube-api.md](contracts/youtube-api.md).
- **Alternatives considered**: None are viable. Browser automation of YouTube Studio is brittle and against the Terms of Service.

## R5. Proving which events this app created (FR-009, SC-005)

- **Decision**: The **local database is the source of truth for ownership**. The app only reads, updates or deletes broadcast ids that it recorded at insert time. It never enumerates the channel to decide what to delete.
- **Crash between insert and commit** (duplicate risk): before calling `insert`, the occurrence is committed in state `creating` with an `intent_at` timestamp. On the next run, each `creating` occurrence is recovered by listing the channel's upcoming broadcasts (`mine=true`, `broadcastStatus=upcoming`, 1 unit per page). The app adopts a broadcast **only if** exactly one is untracked, has identical title and `scheduledStartTime`, **and** has `snippet.publishedAt ≥ intent_at − 2 min`. A manual event created earlier therefore cannot be adopted. If none match, the insert is retried. If more than one matches, the occurrence moves to `failed` with reason `ambiguous_recovery` and the owner is notified.
- **Alternatives considered**: Putting a marker in the public description was rejected because it is visible to the audience. Broadcasts have no hidden tag field.
- **Related (004 S6)**: the same `list_upcoming` call also detects hand-made livestreams within ±15 min of a pending occurrence. They block the create (`exists_external`) and are never modified.

## R6. Respecting manual edits and deletes (edge case, spec assumption)

- **Decision**: After each successful write, store a `last_written_hash` of the fields the app manages (title, description, start, end, privacy). Before every update or delete, fetch the broadcast:
  - If it is **gone (404 / absent from list)**, the occurrence becomes `owner_deleted` and is never recreated.
  - If **remote hash ≠ last_written_hash**, it becomes `owner_modified`. The app stops managing it, logs it, and does not overwrite it.
  - If **`lifeCycleStatus` is not in {`created`, `ready`}** (already live or complete), it is left alone and marked `past`.
  - The owner can hand an event back to the app with `livestream-scheduler occurrence reclaim <id>`.
- **Rationale**: This matches the spec default ("respected by default, not recreated") and FR-009. Reads cost 1 unit, batched 50 ids per call.

## R7. Safe reconciliation (no mass deletion)

- **Decision**: Each run is a pure **plan** step (desired vs. recorded → list of actions) followed by an **execute** step. Safety rules:
  1. If the feed fetch or parse **fails**, the run fails and *no* removals are planned.
  2. If the feed parses but would remove **more than `safety.max_removals_per_run`** (default 5) or **every** active occurrence, removals are held, the owner is notified, and `sync --allow-mass-removal` is needed to proceed.
  3. Actions execute in this order: deletes, updates, then creates by ascending start. When quota runs out, the *latest* streams are the ones deferred.
- **Rationale**: Calendar feeds sometimes return empty or partial bodies. Without these guards, a bad fetch would wipe every public upcoming event.

## R8. Failures, retries and quota (FR-013)

- **Decision**: Errors map to these classes:
  - `auth` (`invalid_grant`, 401) aborts the run, sets the connection to `needs_reauth`, and notifies the owner.
  - `quota` (`quotaExceeded`, `rateLimitExceeded`, `userRequestsExceedRateLimit`) stops all further writes. Remaining actions stay `pending` with `deferred_reason=quota` and are retried on the next run.
  - `transient` (5xx, timeouts, connection errors) is retried in-run up to 3 times with exponential backoff and jitter, then left `pending`.
  - `permanent` (`liveStreamingNotEnabled`, `invalidScheduledStartTime`, validation errors) marks that occurrence `failed` with a plain-language reason. Other occurrences continue. `liveStreamingNotEnabled` also aborts the run, because no other insert can succeed.
- **Rationale**: Every retry is idempotent because the plan is recomputed from the DB on each run (R5).

## R9. OAuth and credential protection (FR-001, FR-002, FR-015)

- **Decision**:
  - `google-auth-oauthlib` `InstalledAppFlow` with a loopback redirect. A `--no-browser` flag prints the URL for headless hosts.
  - Scope: `https://www.googleapis.com/auth/youtube.force-ssl`.
  - The refresh token is stored in `<state_dir>/token.json` (`/var/lib/livestream-scheduler/` under systemd via `$STATE_DIRECTORY`, otherwise the `platformdirs` user state dir) with mode `0600`, and the app refuses to start if the permissions are wider.
  - `connect` checks that `channels.list(mine=true)` returns the configured handle (`@minnehahaumc`, from `snippet.customUrl`, case-insensitive), then records the channel id. The handle is checked once and the stable `UC…` id is pinned. Handles can be renamed, ids cannot. Every run checks that the token still resolves to that channel id, which guarantees "exactly one specific channel".
  - `disconnect` calls `https://oauth2.googleapis.com/revoke` and deletes the token file.
  - A logging filter redacts anything matching token, `client_secret` or `Authorization` patterns.
- **Important operational note**: the OAuth client is registered in a free Google Cloud Console project (API registration only; the app itself runs on the owner's home Ubuntu server). OAuth apps in **"Testing"** publishing status issue refresh tokens that **expire after 7 days**. The quickstart tells the owner to set the consent screen to **"In production"**. Unverified is fine for personal use. In Testing status, the weekly expiry would surface as weekly `needs_reauth` notifications.
- **Alternatives considered**: OS keyring (`keyring`) was rejected because it is unavailable to a headless systemd service. Service accounts were rejected because the YouTube Data API does not support them for channel actions.

## R10. Notifications (FR-012, SC-006)

- **Decision**: Email via stdlib `smtplib` (STARTTLS or SSL). The SMTP password comes from a systemd credential (`smtp-password`), or an env var or file named in config. It is never stored in YAML. The app notifies on **state transitions** (success→failure, failure→recovered, connection→`needs_reauth`, mass removal held, overlap conflict) and sends at most one reminder per open problem per 24 h, so hourly runs do not spam the owner. With hourly cron, the owner hears about a problem within one run (≤ 1 h).
- **Alternatives considered**: Push or webhook (ntfy, Slack) is a straightforward later addition behind the same `Notifier` interface.

## R11. Overlapping occurrences (edge case)

- **Decision**: Two desired occurrences overlap when their `[start, end)` ranges intersect. The earlier-starting one is scheduled. The other is put in `conflict` and the owner is notified, unless config `overlaps: allow`, a `yt.allow-overlap: yes` directive on the event, or `occurrence approve <id>` allows it.

## R12. Persistence

- **Decision**: **SQLite** (stdlib `sqlite3`, WAL mode, `PRAGMA foreign_keys=ON`) at `~/.local/state/livestream-scheduler/state.db`. A `schema_version` table drives forward-only SQL migrations. There is no ORM.
- **Rationale**: Single user, single process, a few hundred rows. Zero ops. Transactions give the crash-safety R5 relies on.

## R13. Scheduling the runs (FR-006) and concurrency

- **Decision** (owner direction 2026-10-08: *systemd timer over cron*): a **system-level** `livestream-scheduler.timer` (`OnCalendar=hourly`, `Persistent=true`, `RandomizedDelaySec=5min`) starts a `Type=oneshot` `livestream-scheduler.service`. The service runs as a dedicated system user with `StateDirectory=`, `ConfigurationDirectory=`, `LoadCredential=` and hardening options. Full units are in [contracts/deployment.md](contracts/deployment.md).
  - `Persistent=true` runs a missed activation at boot, covering the "down for several days" edge case together with full-horizon reconciliation.
  - systemd never starts a second instance of a running oneshot unit. `sync` still takes `fcntl.flock` on `state.lock`, so a manual `lss sync` during a timer run exits 0 with "already running".
  - `SuccessExitStatus=1`: a partial run (quota deferral) is expected operation and the owner is emailed by the app. Exit codes 2–5 and 10 mark the unit failed and are visible in `systemctl --failed`.
- **Rationale**:
  - Journald captures logs with no redirection plumbing.
  - `LoadCredential=` delivers secrets without env files, which supports FR-015.
  - `Persistent=` provides catch-up after downtime, which cron lacks.
  - Sandboxing (`ProtectSystem=strict`, `NoNewPrivileges`, …) limits what a compromised dependency could reach.
  - `systemctl list-timers` shows the last and next run.
- **Alternatives considered**:
  - *cron*: rejected by the owner. It also lacks catch-up, credentials and journald.
  - *systemd user units with `loginctl enable-linger`*: simpler on a personal box, but the token would sit in a login user's home, with no `LoadCredential` isolation from other user processes. Documented as a fallback in the quickstart.
  - *An in-process scheduler (APScheduler)*: needs process supervision anyway.

## R14. Libraries and tooling

| Concern | Choice |
|---|---|
| Python | 3.12 (`zoneinfo`, `tomllib`, modern typing) |
| Packaging / env / runner | **uv** for everything (R16): `pyproject.toml` + committed `uv.lock`, Python pinned by `requires-python` (no `.python-version`: dotfiles aren't tracked), console script `livestream-scheduler`, run via `uv run --frozen` |
| CLI | `click` (testable with `CliRunner`) |
| Config | `PyYAML` + `pydantic` v2 models for validation and clear error messages |
| HTTP for ICS | `requests` (already a transitive dependency of google-auth), with `ETag`/`If-None-Match` |
| Paths | systemd `$STATE_DIRECTORY`/`$CONFIGURATION_DIRECTORY`/`$CREDENTIALS_DIRECTORY` first, `platformdirs` fallback for development |
| Tests | `pytest`, `time-machine` (frozen clocks incl. DST), `responses` (ICS HTTP), in-memory `FakeYouTube` |
| Lint / type | `ruff`, `mypy --strict` on `src/` |

## R15. Testing strategy

- **Decision**:
  - The **planner** is a pure function, `plan(desired, recorded, now, config) → actions`. It is exhaustively unit-tested, including DST transitions (America/Chicago March and November), EXDATE, moved instances, overlaps, and mass-removal guards.
  - A **`YouTubePort` protocol** has two implementations, `GoogleYouTube` and `FakeYouTube`. One shared contract test suite runs against the fake always, and against the real adapter with recorded HTTP (`googleapiclient.http.HttpMockSequence`).
  - **Integration tests** run `sync` end to end with an ICS fixture plus `FakeYouTube`, covering every acceptance scenario in the spec: 30 consecutive runs with no duplicates (SC-003), manual edit and delete, quota deferral, and crash-after-insert recovery.
  - An optional **live smoke test** against a throwaway test channel only runs when `LSS_LIVE_TEST=1`.

## R16. uv as the wrapper for building, running and testing

- **Decision** (owner direction 2026-10-08: *wrap it in uv*):
  - **Project**: `pyproject.toml` (build backend `hatchling`), `requires-python = ">=3.12,<3.13"`, and a committed **`uv.lock`**. Dev tools (pytest, ruff, mypy, time-machine, responses) go in `[dependency-groups] dev`.
  - **Developer loop**: `uv sync`, `uv run pytest`, `uv run ruff check`, `uv run mypy src`, `uv run livestream-scheduler …`. `scripts/check.sh` (and the local pre-commit hook) runs `uv sync --locked`, so it fails if the lock is stale. There is no hosted CI, because `.github/` is a dotfolder and the owner's rule is that no dotfiles are tracked.
  - **Production runner**: the service's `ExecStart` is `uv run --frozen --no-sync --project /opt/livestream-scheduler livestream-scheduler sync`. The environment is built once at deploy time with `uv sync --frozen --no-dev`, so the hardened, read-only service never writes to the project, and `--frozen` guarantees it runs exactly the locked versions.
  - **Python itself** is uv-managed (`uv python install 3.12`) into `/opt/livestream-scheduler/.uv-python` via `UV_PYTHON_INSTALL_DIR`. It is readable by the service user and independent of the distro's Python.
  - **uv binary**: a pinned version installed to `/usr/local/bin/uv`, recorded in the deploy docs. Upgrades are deliberate.
- **Rationale**: One tool gives reproducible installs, matching dev and prod environments, managed interpreters, and a single entry-point convention.
- **Alternatives considered**:
  - *`uv tool install .`*: installs into a per-user tool dir. That is awkward for a system user with `ProtectHome`, and it doesn't honor `uv.lock` the same way. It is fine for a personal user-unit setup.
  - *A pre-built venv invoked directly (`.venv/bin/livestream-scheduler`)*: it works, but the owner asked for uv to be the wrapper. `uv run --no-sync` costs only milliseconds.
  - *A PEX or shiv zipapp*: an extra build step for no benefit here.

## R17. Configuration repository, separate from the application (FR-018)

- **Decision**:
  - The church's settings live in an owner-controlled git repository, e.g. `minnehaha-livestream-config`, laid out as:

    ```text
    config.yaml                 # the YAML in contracts/config-schema.md, secret *references* only
    templates/                  # owner templates/snippets (override bundled defaults)
    README.md                   # what each file is; how to deploy changes
    gitignore.example           # optional ignore list (credentials/, client_secret*.json, token*, *.age, backups/); the secret-scan guard is the real protection
    ```

  - The app repo ships a seed in `examples/config-repo/`.
  - On the server, `/etc/livestream-scheduler/` **is a checkout** of that repo (root-owned, group `livestream-scheduler`, 0750). `credentials/` sits beside the checkout under `/etc/livestream-scheduler-credentials/` (root, 0700), so a `git clean` or re-clone can never touch secrets.
  - **Updating the server's config** (`sudo deploy/install.sh config-pull [--ref <branch|tag|sha>]`):
    1. Fetch and check out the ref into a **staging** worktree.
    2. Run `livestream-scheduler config check` and `templates check` against the staging dir, as the service user.
    3. Only if both pass, atomically switch `/etc/livestream-scheduler` to the new commit; otherwise leave it unchanged and exit non-zero (FR-018).
    4. Print the commit now active. `status` shows it too (`config_commit` is read from `.git/HEAD` at run start and recorded on the `run` row).
  - **Secret-scan guard**: `config check` fails if the config dir contains files matching `credentials/`, `client_secret*.json`, `token*.json` or `*.age`, or if any YAML value looks like a secret (a URL with `/ical/` or `private-`, `ya29.`, `GOCSPX-`). This keeps SC-009.
- **Rationale**: Changes are reviewable and reversible, and the repo can be rebuilt on any machine. Keeping app code and church data separate means app upgrades never conflict with template edits. Validate-then-switch gives safe roll-forward.
- **Alternatives considered**:
  - *Config inside the app repo*: it mixes one church's data with general code and makes upstream releases awkward.
  - *Editing on the server only*: no history or review, and it's lost with the disk.
  - *Ansible or another config-management tool*: too heavy for one home server (Principle IV).

## R18. Backup and restore (FR-019, FR-020, FR-021)

- **Decision**:
  - `livestream-scheduler backup [--output PATH] [--include-secrets]` writes `lss-backup-<UTC timestamp>-v<app version>.tar.gz`. It contains:
    - `manifest.json`: app version, schema version, channel id/handle, created_at, config commit, file list with SHA-256, `secrets_included` flag
    - `state.db`: a consistent snapshot via SQLite's online backup API (`sqlite3.Connection.backup`), safe while the timer runs
    - `config/`: a copy of the active config and templates, including the commit id
  - **Secrets excluded by default**: no `token.json` and no credentials.
  - **With `--include-secrets`**: `token.json` and the credential files are added, and the **whole archive** is encrypted with **age** in passphrase mode (`age -p`; Ubuntu package `age`). The output is `.tar.gz.age`. The passphrase is entered interactively: `age -p` only reads passphrases from a terminal, so encrypted backups cannot run unattended (found during implementation, 2026-10-08). The daily timer backups never include secrets, so they are unaffected. Without age installed, or without a terminal, `--include-secrets` refuses to run.
  - `livestream-scheduler restore PATH [--force]`:
    1. Decrypt if needed (a wrong passphrase means nothing is written).
    2. Verify the manifest checksums.
    3. **Refuse** if the manifest's `schema_version` > the installed schema, or its app version is newer (FR-021).
    4. Refuse if the backup's `channel_id` ≠ the configured `youtube.channel_id`/handle.
    5. Refuse if a `state.db` already exists with runs newer than the backup, unless `--force`.
    6. Take the lock, place `state.db` (and the secrets if present) with correct owners and modes (0600), and run forward migrations.
    7. Report what to supply manually (credentials, or `lss connect` if there's no token).

    Restored `config/` is **not** applied automatically: the config repo is authoritative. It is reported for comparison and can be applied with `--apply-config`.
  - **Automatic backups**: `livestream-scheduler-backup.timer` (`OnCalendar=daily`, `Persistent=true`) runs `backup --output /var/backups/livestream-scheduler/` (no secrets) and prunes to `backup.keep` (default 14). Each backup is recorded in the run log, and a backup failure triggers a notification (`problem_key=backup`).
- **Restoring an older backup** (spec edge case): livestreams created after the backup aren't in `broadcast`, so the 001 FR-017 guard treats them as hand-made (`exists_external`). That is safe, with no duplicates, and the owner is told once.
- **Lost state without a backup**: the same guard applies. `status` reports "N upcoming livestreams on the channel are not managed (no record)". This is detected by `list_upcoming` vs `broadcast` when the DB is empty but the channel has upcoming broadcasts.
- **Rationale**: `state.db` holds the ownership proof (R5) that makes the app safe, so losing it is the real risk. The SQLite online backup avoids copying a DB mid-write. Encryption with age is portable across machines, unlike host-bound systemd-creds encryption, and `age` is a single small, widely packaged tool.
- **Alternatives considered**:
  - *A raw copy of `/var/lib/...`*: can capture a torn WAL.
  - *Encrypting with systemd-creds*: tied to the host or TPM, so it defeats migration.
  - *GPG*: heavier key management for one owner.
  - *Python `cryptography` or pyrage*: adds a compiled dependency for a rarely used path.
  - *Off-site copies*: out of scope. The quickstart recommends copying `/var/backups/livestream-scheduler/` to a second device.

## R19. OAuth client secret as a credential (FR-022)

- **Decision**: Config key `google.client_secret: {credential: oauth-client}` replaces `google.client_secrets_file`. The service unit adds `LoadCredential=oauth-client:/etc/livestream-scheduler-credentials/oauth-client.json`. `auth.py` loads it with `InstalledAppFlow.from_client_config(json.loads(...))`. `{file: path}` (0600/0400) and `{env: VAR}` are still allowed for development.
- **Rationale**: This brings the last secret under the same mechanism (Constitution Principle III). Previously the file sat group-readable (0640) in the config dir, so it would have ended up in the config repo.

## R20. Secrets at rest

- **Decision**: Secrets are protected by file ownership and permissions in `/etc/livestream-scheduler-credentials/` (root, 0700; files 0600), delivered by `LoadCredential=`. **Optional hardening**, documented but not the default: `systemd-creds encrypt` + `LoadCredentialEncrypted=` binds secrets to this host's key or TPM. If used, moving servers requires re-entering secrets, or restoring them from an `--include-secrets` backup taken before the move.
- **Rationale**: For a single-owner home server, permissions plus disk encryption (if any) are adequate. Making host-bound encryption the default would break the portability goal (FR-021, SC-008).
