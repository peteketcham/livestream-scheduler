# Implementation Plan: YouTube Livestream Scheduler

**Branch**: `001-youtube-livestream-scheduler` | **Date**: 2026-10-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-youtube-livestream-scheduler/spec.md`

## Summary

A single-owner Python command-line tool turns stream events in an owner-maintained calendar into scheduled YouTube live broadcasts. Cron runs `livestream-scheduler sync` hourly. Each run:
1. Fetches the calendar's ICS feed.
2. Expands recurrences within a 4-week horizon in the event's own time zone.
3. Reconciles those occurrences against a local SQLite record of the broadcasts this app created, using a pure planner.
4. Calls YouTube Data API v3 `liveBroadcasts` to create, update or delete only broadcasts it owns.

Repeat runs are idempotent through stable occurrence keys and crash-safe insert intents. Manual edits on YouTube are detected by hash and respected. Quota or transient failures are deferred to the next run. Every run is recorded for `status`/`runs`, and the owner is emailed on problem state changes.

## Technical Context

**Language/Version**: Python 3.12

**Repository rule** (owner, 2026-10-08): **no dotfiles or dotfolders are tracked, except `.gitignore`**. There is no `.python-version` or `.github/`. `.gitignore` holds the standard ignores, and `.git/info/exclude` blocks every other dotfile with `.*`, and quality gates run through `scripts/check.sh` plus a local pre-commit hook instead of hosted CI.

**Packaging/Runner**: **uv**, with a committed `uv.lock`, a uv-managed Python 3.12, and `uv run --frozen` in development, CI and production (research R16).

**Primary Dependencies**: google-api-python-client, google-auth, google-auth-oauthlib, icalendar 6.x, recurring-ical-events 3.x, click, pydantic 2, PyYAML, requests, platformdirs (see [research.md](research.md) R14)

**Storage**: SQLite (stdlib `sqlite3`, WAL) for app state. The OAuth token is in a separate `0600` JSON file. Config is YAML.

**Testing**: pytest, time-machine, responses. The in-memory `FakeYouTube` and the real adapter share one contract suite. An optional live smoke test is gated by `LSS_LIVE_TEST=1`.

**Target Platform**: The owner's **Ubuntu Server at home** (24.04 LTS recommended, systemd 255; 22.04 LTS with systemd 249 is **not** supported because it lacks the needed credential features). Self-hosted, not cloud. It runs as a hardened system service from an hourly **systemd timer** (research R13, [contracts/deployment.md](contracts/deployment.md)). macOS is supported for development and tests only.

**Project Type**: CLI application (single project)

**Performance Goals**: A `sync` with no changes finishes in < 10 s and costs ≤ 5 API quota units. The first sync for a 4-week horizon at ~3 streams/week uses ≲ 1,000 units (default daily quota is 10,000).

**Constraints**:
- No duplicate broadcasts across ≥ 30 runs (SC-003).
- Never write to broadcasts the app did not create (SC-005).
- Changes are reflected in ≤ 24 h (SC-004). The bound is ICS-feed lag plus the 1 h timer (+ ≤ 5 min randomized delay).
- Failure notification ≤ 1 h after detection (SC-006).
- Secrets never appear in logs, DB, or email (FR-015).
- A failed or empty feed must never cause mass deletion.

**Scale/Scope**: 1 owner, 1 channel (@minnehahaumc, Minnehaha UMC), 1 calendar, tens of occurrences in the horizon, a few hundred historical rows.

All Technical Context items are resolved. No NEEDS CLARIFICATION remain: FR-016 was settled 2026-10-08 as an external calendar, recorded in spec.md "Clarifications".

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is still the **unfilled template**: there are no ratified principles and no version. There are therefore **no project gates to violate**, and the gate passes by default. To avoid passing vacuously, this plan holds itself to the following baseline. It is not ratified, and it should be replaced by running `/speckit-constitution`.

| Baseline principle | How this plan satisfies it | Pre-design | Post-design |
|---|---|---|---|
| Test-first, with core logic testable without network | Pure `planner`. `YouTubePort` protocol + `FakeYouTube`. ICS fixtures. One acceptance test per spec scenario. | ✅ | ✅ |
| Simplicity / YAGNI | One package. SQLite, no ORM. A systemd timer and oneshot service, not a daemon. No web UI. Single calendar adapter. | ✅ | ✅ |
| Safety of a public channel | DB-proven ownership (R5). Manual-change detection (R6). Mass-removal hold (R7). `--dry-run`. | ✅ | ✅ |
| Security of credentials | Every secret, including the OAuth client, comes through systemd credentials (R19). `0600` token file with permission check. Log redaction. Secret ICS URL never stored (only hashed). A secret-scan guard on the config repo. Backups exclude secrets unless age-encrypted. | ✅ | ✅ |
| Portability and recovery (FR-018–FR-021) | Config lives in a separate git repo, validated then switched (R17). Daily SQLite online-snapshot backups, plus restore with version and channel checks (R18). A documented server move. | ✅ | ✅ |
| Observability | `run`/`run_item` records. Stable exit codes, mapped to unit state via `SuccessExitStatus=1`. `--json`. journald-aware logs. `systemctl list-timers`. | ✅ | ✅ |
| Development workflow | Conventional Commits (owner direction). uv for every build, run and test step. | ✅ | ✅ |

**Post-design re-check (after Phase 1)**: the data model, contracts and quickstart introduce no additional projects, services or abstractions beyond the single `YouTubePort` seam needed for testing. No violations, so Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-youtube-livestream-scheduler/
├── plan.md              # This file
├── research.md          # Phase 0: decisions R1–R15
├── data-model.md        # Phase 1: SQLite schema + occurrence state machine
├── quickstart.md        # Phase 1: setup + validation scenarios
├── contracts/
│   ├── cli.md               # commands, exit codes, JSON, emails
│   ├── config-schema.md     # YAML config contract
│   ├── calendar-mapping.md  # ICS → occurrence rules, identity, directives
│   ├── youtube-port.md      # internal YouTube boundary + error/quota contract
│   └── deployment.md        # systemd units, uv runner, host layout, admin wrapper
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks; not created here)
```

### Source Code (repository root)

```text
pyproject.toml                 # uv project (hatchling); console script livestream-scheduler
uv.lock                        # committed; production uses `uv run --frozen`
scripts/
├── check.sh                   # quality gates: uv sync --locked, ruff, mypy, pytest (replaces hosted CI)
└── install-git-hooks.sh       # writes an untracked .git/hooks/pre-commit that runs check.sh --fast
deploy/
├── systemd/livestream-scheduler.service   # contracts/deployment.md
├── systemd/livestream-scheduler.timer
├── systemd/livestream-scheduler-backup.service   # daily backup (research R18)
├── systemd/livestream-scheduler-backup.timer
├── install.sh                 # install / config-pull / restore (Ubuntu 24.04)
└── lss                        # admin wrapper: runs CLI as the service user via systemd-run
examples/
├── config.yaml / dev-config.yaml
└── config-repo/               # seed for the owner's separate config repository (research R17)
examples/
└── config.yaml
src/livestream_scheduler/
├── __init__.py
├── cli.py                     # click commands (contracts/cli.md)
├── config.py                  # pydantic models, load/validate (contracts/config-schema.md)
├── paths.py                   # $STATE_DIRECTORY/$CONFIGURATION_DIRECTORY/$CREDENTIALS_DIRECTORY → platformdirs fallback; 0600 checks
├── secrets.py                 # resolve credential:/env:/file: secret references
├── backup.py                  # backup/restore: SQLite online snapshot, manifest, age encryption (R18)
├── secretscan.py              # config-dir secret-scan guard (R17, SC-009)
├── logging.py                 # stderr logging + secret-redaction filter
├── lock.py                    # fcntl run lock
├── auth.py                    # OAuth connect/refresh/revoke, token file
├── db/
│   ├── schema/0001_init.sql
│   ├── migrate.py
│   └── repo.py                # typed accessors for data-model tables
├── calendar/
│   ├── fetch.py               # HTTP (ETag) / file source
│   ├── expand.py              # icalendar + recurring-ical-events, window, keys
│   └── mapping.py             # event → DesiredOccurrence, directives, HTML strip
├── youtube/
│   ├── port.py                # YouTubePort protocol, Broadcast/BroadcastSpec, errors
│   ├── google_adapter.py      # GoogleYouTube (real API, error mapping, retries)
│   └── fake.py                # FakeYouTube (in-memory, for tests)
├── sync/
│   ├── planner.py             # pure: desired × recorded × now → [Action]
│   ├── executor.py            # applies actions via YouTubePort, quota/defer logic
│   ├── recovery.py            # R5 creating-state recovery
│   └── run.py                 # orchestrates one sync, records run/run_items
└── notify.py                  # SMTP notifier + problem dedup

tests/
├── fixtures/ics/              # weekly, overrides, exdate, dst, all-day, html-desc, empty …
├── unit/                      # planner, mapping, expand (DST), config, redaction
├── contract/                  # test_youtube_port.py run against Fake + recorded Google HTTP
├── integration/               # sync end-to-end on SQLite tmpdir + FakeYouTube; acceptance tests
└── live/                      # opt-in real-channel smoke test
```

**Structure Decision**: This is a single Python package (`src/` layout) with a `tests/` tree split by unit, contract, integration and live. There is no frontend or service split, because the owner chose CLI + cron. The only internal seam is `youtube/port.py`. It exists so the engine can be fully tested without the network and so the engine never touches API objects directly.

## Key Design Points (cross-references)

- **Reconciliation order and safety**: research R7, contracts/cli.md exit code 5.
- **Ownership and duplicate prevention**: research R5, data-model `broadcast` table rule.
- **Manual-change respect**: research R6, occurrence states `owner_modified` / `owner_deleted`.
- **Error to behavior mapping**: contracts/youtube-port.md error contract, research R8.
- **OAuth 7-day token pitfall**: research R9, quickstart prerequisites.

## Complexity Tracking

No constitution violations, so nothing to justify.
