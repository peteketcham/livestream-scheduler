# Contract: Command-Line Interface

Executable: `livestream-scheduler` (console script). Global options apply to every command:

| Option | Default | Meaning |
|---|---|---|
| `--config PATH` | `$LSS_CONFIG` → `$CONFIGURATION_DIRECTORY/config.yaml` → user config dir | YAML config ([config-schema.md](config-schema.md)) |
| `--state-dir PATH` | `$LSS_STATE_DIR` → `$STATE_DIRECTORY` (systemd) → `platformdirs` user state dir | Holds `state.db`, `token.json`, `state.lock` |
| `--json` | off | Machine-readable output on stdout, one JSON document |
| `-v / -q` | | Log verbosity (logs → stderr, secrets redacted) |

**Exit codes** (stable, so systemd (`SuccessExitStatus=1`) and monitoring can rely on them):

| Code | Meaning |
|---|---|
| 0 | Success. Also used when the run was skipped because another run holds the lock. |
| 1 | Partial: run completed, some occurrences deferred or failed |
| 2 | Usage or config validation error |
| 3 | Not connected / needs re-auth / channel not eligible |
| 4 | Calendar feed fetch/parse failure (no changes made) |
| 5 | Safety hold (mass removal blocked) |
| 10 | Internal error |

---

## `connect [--no-browser] [--port N] [--forget-tracked]`

Runs the OAuth consent flow, resolves the channel via `channels.list(mine=true)`, stores the token, and records the channel.
- stdout: `Connected to channel "<title>" (<channel_id>)`
- If the authorized channel's handle is not `youtube.channel_handle`, the token is revoked and discarded, and the command exits 3 with `Authorized channel "<title>" (@<handle>) is not @minnehahaumc; re-run connect and pick the right channel.` Handles are compared case-insensitively.
- If a *different* channel is already tracked, it fails with exit 2 unless `--forget-tracked` is given.
- Satisfies FR-001 and acceptance scenario US1-3.

## `disconnect`

Revokes the token at Google, deletes `token.json`, and clears `channel_connection`. Broadcast and occurrence rows are kept for history. Satisfies FR-002.

## `sync [--dry-run] [--allow-mass-removal] [--trigger timer|manual]`

Runs one reconciliation pass: fetch feed → expand → plan → execute → record run → notify. This is the command the systemd service runs on each timer activation.
- `--dry-run` prints the planned actions and makes no API writes and no DB state changes. A `run` row is still written with outcome `success` and the counters it *would* have produced, flagged `dry_run`.
- Human output is a one-line summary plus one line per action:
  `created  #12  2026-10-14 19:00 America/Chicago  "Weekly Q&A"  → https://youtu.be/<id>`
- When not connected, it exits 3 and makes no API calls (US1-2).

## `status`

Shows the connection (channel title, state), the config path and **config commit** (if a git checkout), the last backup time, any upcoming channel livestreams **not managed** (no record), the feed's last fetch time, the last run's outcome and counters, open problems, and the next 5 scheduled occurrences. Answers SC-007 in a single command.

## `runs [--limit N=10] [--run ID]`

Lists recent runs. With `--run`, it shows that run's `run_item`s with plain-language messages (US3-1, US3-2).

## `occurrences [--state STATE ...] [--all]`

Lists occurrences in the horizon by default, with columns `id, start (owner tz), title, visibility, state, reason, broadcast url`.

## `occurrence skip <id>` / `occurrence unskip <id>`

Sets or clears the local `skip` override. The next `sync` deletes any broadcast this app created for it. Satisfies FR-010. The calendar-native way to skip is to delete that instance in the calendar.

## `occurrence approve <id>`

Approves an occurrence held in `conflict` because it overlaps another (spec edge case).

## `occurrence reclaim <id>`

Hands an `owner_modified` or `owner_deleted` occurrence back to the app. On the next sync the app overwrites the broadcast, or recreates it if it was deleted.

## `occurrence retry <id>`

Moves a `failed` occurrence back to `pending`.

## `config check`

Validates the config, fetches and parses the feed, and prints the occurrences the current horizon would produce, with mapping warnings (truncation, all-day skipped, unknown directive). It does not contact YouTube.

## `backup [--output DIR] [--include-secrets] [--prune]`

Writes a backup archive (research R18). Without `--include-secrets` it contains `manifest.json`, `state.db` (online snapshot) and `config/`. With it, the token and credentials are added and the whole archive is age-encrypted. `--prune` keeps the newest `backup.keep`. stdout gives the archive path and size. Exit 2 if `--include-secrets` is used without `age` installed or outside a terminal (age prompts for the passphrase).

## `restore PATH [--force] [--apply-config]`

Decrypts if needed, verifies the manifest, and refuses (exit 2) on: newer schema or app version, channel mismatch, wrong passphrase, or existing newer state without `--force`. Then it places the files with 0600 modes, runs migrations, and reports what's still needed (credentials or `connect`). It never contacts YouTube.

## `notify test`

Sends a test email using the configured SMTP settings.

---

## JSON shapes (`--json`)

```json
// sync / runs --run
{"run": {"id": 42, "started_at": "…Z", "finished_at": "…Z", "outcome": "partial",
         "counts": {"created": 3, "updated": 1, "removed": 0, "skipped": 0, "deferred": 2, "failed": 0},
         "error_class": "quota", "error_message": "YouTube daily limit reached; 2 events will be retried next run."},
 "items": [{"occurrence_id": 12, "action": "create", "result": "ok", "broadcast_id": "abc", "message": null}]}

// occurrences
{"occurrences": [{"id": 12, "key": "uid@google.com|2026-10-15T00:00:00Z", "start": "2026-10-14T19:00:00-05:00",
                  "title": "Weekly Q&A", "visibility": "public", "state": "scheduled", "reason": null,
                  "broadcast_url": "https://youtu.be/abc"}]}
```

## Notification emails (FR-012)

- Subject: `[livestream-scheduler] <PROBLEM|RESOLVED>: <short reason>`. The body includes the channel title, run id, a plain-language reason, the affected occurrences, and the exact command to fix it (for example `livestream-scheduler connect`).
- Triggered on the state transitions defined in research R10.
- Emails never contain tokens, client secrets, or the secret ICS URL.
