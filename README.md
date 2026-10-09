# livestream-scheduler

Automatically schedules YouTube livestreams for **Minnehaha UMC**
([@minnehahaumc](https://www.youtube.com/@minnehahaumc)) from the church's stream calendar.

- The stream calendar's iCal feed is the single source of truth. Every event (and every instance of a
  recurring event) in the next 4 weeks becomes a scheduled livestream.
- Repeated runs are idempotent:
  - calendar changes update the same videos;
  - deleted events remove only the livestreams this app created;
  - nothing is ever duplicated.
- **Livestreams created by hand are never touched.** If one already exists within 15 minutes of a
  calendar event, the app creates nothing for that event and tells you once.
- Edits you make in YouTube Studio are respected. Use `occurrence reclaim` to hand a livestream back
  to the app.
- Runs hourly from a **systemd timer** on a home **Ubuntu Server 24.04**. Every step uses **uv**.

Specs, plans, and design decisions live in [`specs/`](specs/); start with
[001](specs/001-youtube-livestream-scheduler/spec.md).

## Local development

```bash
uv sync                                   # installs Python 3.12 + locked deps into .venv
scripts/install-git-hooks.sh              # pre-commit runs scripts/check.sh --fast
scripts/check.sh                          # lock check, ruff, mypy --strict, pytest
```

To run against a test channel, copy `examples/dev-config.yaml` to `dev/config.yaml`. `dev/` is
git-ignored. Then:

```bash
export LSS_CONFIG=$PWD/dev/config.yaml LSS_STATE_DIR=$PWD/dev/state
export LSS_CALENDAR_URL='https://calendar.google.com/calendar/ical/…/basic.ics' LSS_SMTP_PASSWORD='…'
uv run livestream-scheduler config check
uv run livestream-scheduler connect
uv run livestream-scheduler sync --dry-run
```

## Home-server deployment

See the [quickstart](specs/001-youtube-livestream-scheduler/quickstart.md) and
[deployment contract](specs/001-youtube-livestream-scheduler/contracts/deployment.md). In short:

```bash
git clone --branch vX.Y.Z https://github.com/peteketcham/livestream-scheduler.git /tmp/lss
sudo /tmp/lss/deploy/install.sh vX.Y.Z --config-repo <your config repo URL>
lss config check && lss notify test
lss connect --no-browser --port 8765      # through `ssh -L 8765:localhost:8765 <server>`
lss sync --dry-run && lss sync
sudo systemctl enable --now livestream-scheduler.timer livestream-scheduler-backup.timer
```

`lss` runs any command as the service user, with the same credentials as the timer. Examples:
`lss status`, `lss runs`, `lss occurrences`, `lss occurrence skip 12`.

### What is the "Google Cloud project" for?

YouTube only lets programs manage a channel after a **free API registration**:
1. Create a project in the Google Cloud Console.
2. Enable *YouTube Data API v3*.
3. Create an OAuth client of type **Desktop app**.
4. Set the consent screen to **In production**. In "Testing" status, logins expire every 7 days.

That is all the project is for. Nothing runs in Google's cloud and no billing is needed. The app
runs on your own server.

### Configuration repository

Keep `config.yaml` and `templates/` in a **separate private git repository**, seeded from
[`examples/config-repo/`](examples/config-repo/). It holds no secrets, only references such as
`{credential: calendar-url}`. To change settings:
1. Edit, commit and push.
2. On the server, run `sudo deploy/install.sh config-pull`. It validates the new config first and
   only switches to it if it passes.

`config check` refuses a config directory that contains anything secret-looking.

### Secrets

The OAuth client, the calendar's secret address and the SMTP password live in
`/etc/livestream-scheduler-credentials/` (root, 0600). systemd passes them in with
`LoadCredential=`. The YouTube login token lives in `/var/lib/livestream-scheduler/token.json`
(0600). Logs and emails are redacted.

### Backups and moving servers

A daily timer writes backups to `/var/backups/livestream-scheduler/` and keeps the newest 14.
These backups never contain secrets. Copy them to another device from time to time.

To move to a new server:
1. On the old server: `lss backup --include-secrets`. This needs `age` and a terminal; it asks for
   a passphrase.
2. Install on the new server.
3. Run `sudo deploy/install.sh restore <file>`.
4. Run `lss sync --dry-run`. It should plan 0 creates.
5. Enable the timers on the new server only.

Never run both servers' timers at the same time.

## Commands

| Command | What it does |
|---|---|
| `connect` / `disconnect` | Authorize or revoke the channel. Only @minnehahaumc is accepted. |
| `sync [--dry-run] [--allow-mass-removal]` | One reconciliation pass. This is what the timer runs. |
| `status` | Connection, config commit, last run, last backup, open problems, the next 5 livestreams |
| `runs [--run ID]` | Run history and per-item details |
| `occurrences [--state …]` | What is scheduled, with reasons and links |
| `occurrence skip/unskip/approve/reclaim/retry ID` | Per-occurrence overrides |
| `config check` | Validate config, scan for secrets, preview the next 4 weeks (does not contact YouTube) |
| `notify test` | Send a test email |
| `backup` / `restore` | See above |

Add `--json` to any command for machine-readable output. Exit codes:

| Code | Meaning |
|---|---|
| 0 | OK |
| 1 | Partial (something deferred or failed) |
| 2 | Usage or config error |
| 3 | Not connected or needs re-auth |
| 4 | Calendar feed problem (nothing changed) |
| 5 | Removals held for safety |
| 10 | Internal error |

## Contributing

- Conventional Commits (`feat(sync): …`), signed.
- `scripts/check.sh` must pass before every commit.
- Dotfiles are not tracked, except `.gitignore`.
