# Contract: Deployment (systemd timer + uv)

Owner decisions (2026-10-08): the app is run by a **systemd timer, not cron**, and the Python app is **wrapped in uv** for installing, running and testing. Rationale and alternatives are in [research.md](../research.md) R13 and R16.

The target is the owner's **Ubuntu Server at home**, 24.04 LTS (systemd 255). systemd ≥ 250 is required for the `LoadCredential=` features used here, which rules out Ubuntu 22.04 (systemd 249). It is self-hosted: the only network need is **outbound HTTPS** to Google (YouTube API, OAuth), the calendar host, umcdiscipleship.org (003) and the SMTP server. No inbound ports, port forwarding, dynamic DNS or public IP are needed.

**Home-server prerequisites** (checked by `deploy/install.sh`):
- `timedatectl` shows `System clock synchronized: yes`. Accurate time matters for scheduling and OAuth.
- Packages: `git`, `curl`, `ca-certificates`, `sqlite3` (for inspection). uv installs Python itself.
- Recommended: `unattended-upgrades` for security patches. The timer's `Persistent=true` catches up after power cuts or reboots.

**About "Google Cloud"**: YouTube API access requires creating a free project in the **Google Cloud Console** (console.cloud.google.com) to enable the YouTube Data API and get an OAuth client ID. That is only an API registration: nothing runs in Google's cloud, and no billing account is needed. Development and tests also run on macOS, but deployment is Linux-only.

## Layout on the host

| Path | Owner / mode | Contents |
|---|---|---|
| `/opt/livestream-scheduler/` | root, 0755, read-only to the service | Git checkout at a release tag, `uv.lock`, `.venv/` (built at deploy time) |
| `/opt/livestream-scheduler/.uv-python/` | root, 0755 | uv-managed CPython 3.12 (`UV_PYTHON_INSTALL_DIR`) |
| `/etc/livestream-scheduler/` | root:livestream-scheduler, 0750 | **Git checkout of the owner's config repo** (research R17): `config.yaml`, `templates/`. It holds no secrets. |
| `/etc/livestream-scheduler-credentials/` | root, 0700 | `oauth-client.json`, `calendar-url`, `smtp-password` and optionally `backup-passphrase` (all 0600). Passed with `LoadCredential=`. It is kept **outside** the config checkout, so git operations can't touch it. |
| `/var/backups/livestream-scheduler/` | livestream-scheduler, 0700 | Daily backups (research R18), secrets excluded |
| `/var/lib/livestream-scheduler/` | livestream-scheduler, 0700 (`StateDirectory=`) | `state.db`, `token.json` (0600), `state.lock` |
| `/var/cache/livestream-scheduler/` | livestream-scheduler (`CacheDirectory=`) | `UV_CACHE_DIR` |

The service runs as a dedicated system user, `livestream-scheduler` (`useradd --system --no-create-home --shell /usr/sbin/nologin`).

## `deploy/systemd/livestream-scheduler.service`

```ini
[Unit]
Description=Schedule Minnehaha UMC YouTube livestreams
Documentation=file:/opt/livestream-scheduler/README.md
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=livestream-scheduler
Group=livestream-scheduler
WorkingDirectory=/opt/livestream-scheduler
Environment=UV_PYTHON_INSTALL_DIR=/opt/livestream-scheduler/.uv-python
Environment=UV_CACHE_DIR=/var/cache/livestream-scheduler
Environment=UV_NO_SYNC=1
Environment=LSS_CONFIG=/etc/livestream-scheduler/config.yaml
ExecStart=/usr/local/bin/uv run --frozen --no-sync --project /opt/livestream-scheduler \
          livestream-scheduler sync --trigger timer
StateDirectory=livestream-scheduler
StateDirectoryMode=0700
CacheDirectory=livestream-scheduler
ConfigurationDirectory=livestream-scheduler
LoadCredential=oauth-client:/etc/livestream-scheduler-credentials/oauth-client.json
LoadCredential=calendar-url:/etc/livestream-scheduler-credentials/calendar-url
LoadCredential=smtp-password:/etc/livestream-scheduler-credentials/smtp-password
# exit 1 = partial (deferred/failed occurrences; owner already emailed) → not a unit failure
SuccessExitStatus=1
TimeoutStartSec=15min
# Hardening
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
RestrictNamespaces=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
SystemCallArchitectures=native
UMask=0077
```

## `deploy/systemd/livestream-scheduler.timer`

```ini
[Unit]
Description=Run livestream-scheduler hourly

[Timer]
OnCalendar=hourly
RandomizedDelaySec=5min
Persistent=true          # catch up after downtime (spec edge case: down for several days)
AccuracySec=1min

[Install]
WantedBy=timers.target
```

## `deploy/systemd/livestream-scheduler-backup.service` / `.timer` (research R18)

The service has the same `[Service]` user, environment and hardening as the main unit, plus `ReadWritePaths=/var/backups/livestream-scheduler` and `ExecStart=… livestream-scheduler backup --output /var/backups/livestream-scheduler --prune`. It has **no** credentials except `oauth-client` (needed only to load config). The timer uses `OnCalendar=daily`, `RandomizedDelaySec=30min` and `Persistent=true`.

## Config repository workflow (research R17)

| Action | Command |
|---|---|
| First install | `sudo deploy/install.sh vX.Y.Z --config-repo <git URL> [--config-ref main]` clones the repo to `/etc/livestream-scheduler` |
| Deploy a config change | Commit and push to the config repo, then on the server `sudo deploy/install.sh config-pull [--ref <ref>]`. It validates in staging and switches only if valid. |
| See what's active | `lss status` shows `config: <repo> @ <short sha>` |
| Roll back | `sudo deploy/install.sh config-pull --ref <older sha>` |

## Move to a new server

1. **Old server**: `lss backup --include-secrets --output /tmp/` (passphrase prompt), then copy the `.tar.gz.age` off the machine. Without `--include-secrets`, plan to re-enter the credentials and run `lss connect`.
2. **New server** (Ubuntu 24.04): `sudo deploy/install.sh vX.Y.Z --config-repo <URL>`. **Do not enable the timer yet.**
3. `sudo deploy/install.sh restore /path/to/backup.tar.gz.age`. This prompts for the passphrase, then runs `livestream-scheduler restore` as the service user, places the credentials, and runs migrations.
4. `lss status` shows the same channel and the expected managed livestream count. `lss sync --dry-run` shows **0 creates** for existing livestreams.
5. Disable the timers on the old server, then `systemctl enable --now livestream-scheduler.timer livestream-scheduler-backup.timer` on the new one.

Never run both servers' timers at once. Each would see the other's new livestreams as hand-made, which is safe but leaves livestreams unmanaged.

## How the app reads its environment

These are added to [cli.md](cli.md) global options:

| Setting | Resolution order |
|---|---|
| Config path | `--config` → `$LSS_CONFIG` → `$CONFIGURATION_DIRECTORY/config.yaml` → user config dir |
| State dir | `--state-dir` → `$LSS_STATE_DIR` → `$STATE_DIRECTORY` (set by systemd) → user state dir |
| Secrets | A config value may reference `credential: <name>` (read from `$CREDENTIALS_DIRECTORY/<name>`), `env: <VAR>`, or `file: <path>` ([config-schema.md](config-schema.md)) |
| Run trigger | `--trigger` → `timer` if `$INVOCATION_ID` is set (systemd) → `manual` |
| Log format | If `$JOURNAL_STREAM` is set, no timestamps and syslog-style `<N>` level prefixes for journald. Otherwise human-readable to stderr. |

## Admin wrapper: `deploy/lss`

Interactive commands (`connect`, `status`, `runs`, `preview`, …) must run as the service user, with the same environment and credentials as the timer. `deploy/lss` is a small shell script:

```text
lss <args…>  ≡  sudo systemd-run --quiet --pty --wait --collect \
                  --uid=livestream-scheduler --gid=livestream-scheduler \
                  -p StateDirectory=livestream-scheduler -p CacheDirectory=livestream-scheduler \
                  -p ConfigurationDirectory=livestream-scheduler \
                  -p LoadCredential=oauth-client:… -p LoadCredential=calendar-url:… -p LoadCredential=smtp-password:… \
                  -E UV_PYTHON_INSTALL_DIR=… -E UV_CACHE_DIR=… -E UV_NO_SYNC=1 -E LSS_CONFIG=… \
                  /usr/local/bin/uv run --frozen --no-sync --project /opt/livestream-scheduler \
                  livestream-scheduler <args…>
```

This ensures `token.json` is created by the right user with the right path and permissions.

## OAuth `connect` on a headless server

Google removed the out-of-band OAuth flow, so the loopback redirect must reach the server:

1. On your laptop: `ssh -L 8765:localhost:8765 <server>`
2. On the server: `lss connect --no-browser --port 8765`. It prints the consent URL.
3. Open the URL in the laptop browser and pick the **Minnehaha UMC** channel. The redirect to `localhost:8765` is tunnelled to the server.

`connect` gains a `--port` option (default: a random free port; fixed when `--no-browser` is used).

## Install, upgrade, uninstall

| Step | Commands (as root) |
|---|---|
| One-shot installer | `sudo deploy/install.sh vX.Y.Z --config-repo <git URL> [--config-ref main]` runs every row below idempotently:<br>• checks the Ubuntu version, systemd ≥ 250 and the time sync<br>• installs `git curl ca-certificates sqlite3 age`<br>• creates the user and directories, installs uv, builds the env<br>• clones the config repo to `/etc/livestream-scheduler`<br>• prompts for any missing credential (the `oauth-client.json` path to copy, `calendar-url` and `smtp-password` with hidden input)<br>• installs both unit pairs and `lss`, leaving the timers **disabled**<br>• prints the `lss connect` instructions<br>Subcommands: `config-pull [--ref]` (R17) and `restore <backup>` (R18). |
| Install uv | Pin the version: `curl -LsSf https://astral.sh/uv/<ver>/install.sh \| env UV_INSTALL_DIR=/usr/local/bin sh` |
| Fetch code | `git clone --branch vX.Y.Z … /opt/livestream-scheduler` |
| Build env | `cd /opt/livestream-scheduler && UV_PYTHON_INSTALL_DIR=$PWD/.uv-python uv sync --frozen --no-dev --python 3.12` |
| Units | `install -m0644 deploy/systemd/* /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now livestream-scheduler.timer livestream-scheduler-backup.timer` (after the dry run) |
| Upgrade | `git -C /opt/livestream-scheduler fetch --tags && git checkout vX.Y.Z && uv sync --frozen --no-dev` (same env vars). The next timer run uses it, and DB migrations run automatically. |
| Uninstall | `lss backup`, then `systemctl disable --now livestream-scheduler.timer livestream-scheduler-backup.timer && lss disconnect`, then remove the paths above |

## Observability

- `systemctl list-timers livestream-scheduler.timer` shows the next and last run.
- `journalctl -u livestream-scheduler` shows the logs (secrets redacted, 001 R9).
- `systemctl status livestream-scheduler` shows the last exit. Exit codes 2–5 and 10 mark the unit `failed` (code 1 does not, via `SuccessExitStatus=1`).
- Optional: `OnFailure=` a unit that emails root, as a backstop if the app cannot send its own email (e.g. a crash before config loads).
