# Quickstart & Validation Guide: YouTube Livestream Scheduler

This guide proves the feature works end to end. Command shapes are in [contracts/cli.md](contracts/cli.md), config keys in [contracts/config-schema.md](contracts/config-schema.md), and calendar rules in [contracts/calendar-mapping.md](contracts/calendar-mapping.md).

## Prerequisites

- **Server**: Ubuntu Server 24.04 LTS on the home network, with sudo access, outbound HTTPS, and the clock synced (`timedatectl`). No inbound ports or port forwarding needed. **Laptop**: SSH access to the server and a browser, used for the one-time Google consent.
- **uv**, at a pinned version, on both machines. uv installs Python 3.12 itself (research R16).
- A YouTube channel **already enabled for live streaming**: @minnehahaumc. Use a **throwaway test channel** for the first live validation.
- **YouTube API registration** (free; nothing is hosted at Google and no billing is needed): in the Google Cloud Console, create a project, enable **YouTube Data API v3**, and create an **OAuth client of type "Desktop app"**. Download its JSON as `client_secret.json`.
- On the OAuth consent screen, set publishing status to **In production**. In "Testing" status, refresh tokens expire every 7 days (research R9). An unverified app is fine for your own account.
- A calendar dedicated to streams, plus its **secret ICS address**. In Google Calendar this is under Settings → *calendar* → Integrate calendar → "Secret address in iCal format".
- SMTP credentials for notifications.

## Local development (macOS or Linux)

```bash
uv sync                                     # creates .venv from uv.lock, installs Python 3.12 if needed
export LSS_CONFIG=$PWD/dev/config.yaml      # dev config uses {env: LSS_CALENDAR_URL}, {env: LSS_SMTP_PASSWORD}
export LSS_STATE_DIR=$PWD/dev/state
export LSS_CALENDAR_URL='https://calendar.google.com/calendar/ical/…/basic.ics'
export LSS_SMTP_PASSWORD='…'
uv run livestream-scheduler config check    # validates config + shows occurrences that would be scheduled
uv run livestream-scheduler connect         # browser consent → must report @minnehahaumc (or your test channel)
uv run livestream-scheduler sync --dry-run
```

## Server deployment (target: < 10 minutes, SC-001)

Paths, units and commands are defined in [contracts/deployment.md](contracts/deployment.md).

**0. Configuration repository (once).** Create a private git repo for the church's settings, e.g. `minnehaha-livestream-config`, seeded from the app's `examples/config-repo/` (`config.yaml`, `templates/`, `README.md`, `gitignore.example`). It holds **no secrets**: only `{credential: …}` references (research R17). Commit and push.

**1. Install on the home server** (Ubuntu 24.04):

```bash
git clone --branch vX.Y.Z <app repo> /tmp/lss && cd /tmp/lss
sudo deploy/install.sh vX.Y.Z --config-repo <config repo URL>
#  → prompts: path to the downloaded OAuth client JSON, the secret calendar URL, the SMTP password
#  → leaves timers disabled and prints the next steps

lss config check && lss notify test        # expect a test email
# one-time consent, tunnelled from the laptop:  ssh -L 8765:localhost:8765 <server>
lss connect --no-browser --port 8765       # open printed URL on laptop, choose Minnehaha UMC
lss sync --dry-run && lss sync
sudo systemctl enable --now livestream-scheduler.timer livestream-scheduler-backup.timer
systemctl list-timers 'livestream-scheduler*'      # next sync within the hour, backup within a day
```

**Changing settings or templates later**: edit in the config repo, commit and push, then run `sudo deploy/install.sh config-pull` on the server. It validates first and keeps the old config if the new one fails.

**Backups and moving servers**: daily backups (no secrets) go to `/var/backups/livestream-scheduler/`. Copy them to another device now and then. To move to a new server, follow "Move to a new server" in contracts/deployment.md.

The manual equivalent of the installer is the "Install, upgrade, uninstall" table in contracts/deployment.md.

**Fallback for a personal machine without root**: install the same two units under `~/.config/systemd/user/`. Remove `User=`, `Group=` and `LoadCredential=` (use `{file: …}` secret references instead), run `loginctl enable-linger $USER`, and use `systemctl --user`. See research R13.

## Automated validation

```bash
scripts/check.sh                           # uv sync --locked + ruff + mypy + pytest (no hosted CI)
uv sync --locked                           # fails if uv.lock is stale
uv run pytest                              # unit + contract (FakeYouTube + recorded HTTP) + integration
uv run pytest tests/integration -k acceptance   # one test per spec acceptance scenario
uv run ruff check && uv run mypy src
LSS_LIVE_TEST=1 uv run pytest tests/live   # optional; real test channel, cleans up after itself
```

Expected: all green. The integration suite runs `sync` against ICS fixtures and `FakeYouTube`, including 30 consecutive no-change runs (SC-003).

## Manual end-to-end scenarios (on the test channel)

| # | Steps | Expected outcome | Proves |
|---|---|---|---|
| 1 | Calendar: weekly recurring event "Weekly Q&A", Tue 19:00 local, 1 h. Run `sync`. | 4 upcoming broadcasts on YouTube Studio → Live → Scheduled, correct title, local time and visibility. `status` lists them. | US1-1, FR-005, SC-002 |
| 2 | Run `sync` twice more. | Each run reports `created 0 updated 0 removed 0`, and there are no new broadcasts on the channel. | US2-1, FR-007, SC-003 |
| 3 | Rename the series and move one instance by 30 min, then `sync`. Note Google ICS lag. Use `calendar.path` with an exported `.ics` to test immediately. | All 4 renamed in place (same video ids). One instance time changed. | US2-2, FR-008, SC-004 |
| 4 | Delete one instance in the calendar, then `sync`. | That broadcast is removed. The others are untouched. | US2-3, FR-010 |
| 5 | `occurrence skip <id>`, then `sync`. Then `occurrence unskip <id>`, then `sync`. | Removed, then recreated (new video id). | FR-010 |
| 6 | In YouTube Studio, create a manual scheduled stream. Also edit the title of one app-created stream. Then `sync`. | Manual stream untouched. The edited one becomes `owner_modified` and is not overwritten. `occurrences` shows the reason. | US2-4, FR-009, SC-005 |
| 7 | Delete an app-created stream in Studio, then `sync`. | Occurrence becomes `owner_deleted` and is **not** recreated. | Edge case: manual change respected |
| 8 | Add an event overlapping "Weekly Q&A", then `sync`. | The later event is held as `conflict`, a warning email is sent, and `occurrence approve <id>` schedules it next run. | Edge case: overlap |
| 9 | Point the `calendar-url` credential at an empty calendar, then `lss sync`. | Exit 5 safety hold, nothing deleted, email sent. `sync --allow-mass-removal` proceeds. | R7 safety |
| 10 | Revoke app access at myaccount.google.com → Security → Third-party access, then `sync`. | Exit 3, no changes, email "reconnect needed" within that run. `connect` fixes it. | US3-2, FR-012, SC-006 |
| 11 | Run `runs` and `runs --run <id>`. | Each run's time, counts, and per-item plain-language messages are shown in under 1 minute. | US3-1, FR-011, SC-007 |
| 12 | Search the journal (`journalctl -u livestream-scheduler`) and a DB dump (`sqlite3 /var/lib/livestream-scheduler/state.db .dump`) for `ya29.`, `refresh_token`, `client_secret` and the ICS URL | No matches. | FR-015 |
| 13 | Create an event at 19:00 on the Tuesday before a DST change and the Tuesday after, then `sync`. | Both show 19:00 local in Studio. Their UTC times differ by 1 h. | FR-014 |
| 14 | `disconnect` | Token revoked and the file deleted. `status` shows "not connected". | FR-002 |
| 15 | `lss backup`, then `tar -tzf` the archive and grep it for `ya29.`, `refresh_token`, `client_secret`, `GOCSPX-` and the ICS URL | `manifest.json`, `state.db` and `config/` only. 0 secret hits. | FR-019, SC-009 |
| 16 | Second VM: `install.sh --config-repo …`, `install.sh restore <backup>.tar.gz.age` (from `lss backup --include-secrets`), `lss sync --dry-run` | 0 creates for existing livestreams, and updates apply to them. No `lss connect` needed. | US4-1, US4-3, FR-021, SC-008 |
| 17 | Restore with the wrong passphrase, then a backup from a newer app version | Both refused, and nothing is written | US4-3, FR-021 |
| 18 | Push a config commit with a template typo, then `install.sh config-pull` | Rejected with `file:line`, and `status` still shows the previous commit | US4-4, FR-018 |
| 19 | Put a `client_secret.json` in the config repo, then `lss config check` | Fails with the secret-scan message | FR-022, SC-009 |

## Cleanup

Delete test broadcasts with `occurrence skip` on each one plus `sync`, or in Studio. Then run `disconnect`.
