# Contract: Configuration File (YAML)

Path: `--config`, `$LSS_CONFIG`, `$CONFIGURATION_DIRECTORY/config.yaml`, or `<user_config_dir>/livestream-scheduler/config.yaml`. In production this file lives in the owner's **configuration repository** (research R17), checked out at `/etc/livestream-scheduler/`. The file is validated by pydantic models. Any unknown key fails validation with exit 2, which catches typos. Secrets are **never** written in this file. They are written as a **secret reference**, one of:
- `{credential: <name>}`: read from `$CREDENTIALS_DIRECTORY/<name>`. This is the systemd `LoadCredential=` path and the production default.
- `{env: <VAR>}`: read from an environment variable (development).
- `{file: <path>}`: read from a file that must be mode 0600 or 0400.

```yaml
version: 1

google:
  client_secret: {credential: oauth-client}   # OAuth "Desktop app" client JSON (research R19); dev: {file: ./dev/client_secret.json}

calendar:
  url: {credential: calendar-url}   # secret ICS URL via systemd LoadCredential (dev: {env: LSS_CALENDAR_URL})
  # path: ./streams.ics             # local file alternative (mutually exclusive with url)
  include:                       # optional; omit = every event in the feed
    summary_prefix: "[LIVE] "    # only events whose title starts with this (prefix is stripped)
    # directive: true            # or: only events containing a `yt.stream: yes` line

defaults:
  timezone: America/Chicago      # IANA (Minneapolis); used for floating (no-TZID) times and for display
  visibility: public             # public | unlisted | private
  made_for_kids: false
  enable_auto_start: false
  enable_auto_stop: false
  enable_dvr: true

youtube:
  channel_handle: "@minnehahaumc"  # required; connect/sync refuse any other channel
  channel_id: UCzwZQ34D3RZEncTf6fAe0hQ  # optional; if set, must also match (stronger than handle)
  stream_id: null                # optional reusable liveStreams id to bind every broadcast to

horizon:
  days: 28                       # FR-005 default 4 weeks; 1..180

overlaps: warn                   # warn (default; hold later one as conflict) | allow

safety:
  min_lead_minutes: 15           # occurrences starting sooner are ignored
  max_removals_per_run: 5        # above this → safety hold (exit 5) unless --allow-mass-removal

notify:
  email_to: owner@example.com    # required (spec assumption: notifications by email)
  email_from: scheduler@example.com
  smtp_host: smtp.example.com
  smtp_port: 587
  smtp_security: starttls        # starttls | ssl | none
  smtp_user: scheduler@example.com
  smtp_password: {credential: smtp-password}   # dev: {env: LSS_SMTP_PASSWORD}
  reminder_hours: 24

retention_days: 90

backup:                          # research R18
  dir: /var/backups/livestream-scheduler
  keep: 14                       # daily backups retained (FR-020)
  passphrase: null               # optional {credential: backup-passphrase} for unattended --include-secrets
```

## Validation rules

| Rule | Error message (example) |
|---|---|
| Exactly one of `calendar.url`, `calendar.path` | `calendar: set exactly one of url, path` |
| Every secret reference resolves at `sync` time | `calendar.url: credential "calendar-url" not found in $CREDENTIALS_DIRECTORY (is LoadCredential= set?)` |
| A plain-string `calendar.url` is accepted, with a warning that it is a secret | |
| `defaults.timezone` must be a valid IANA zone (`zoneinfo`) | `defaults.timezone: unknown time zone "EST5"` |
| `visibility` ∈ {public, unlisted, private} | |
| `horizon.days` in 1..180 | |
| `google.client_secret` resolves to valid OAuth client JSON (`installed.client_id` present) | `google.client_secret: credential "oauth-client" is not OAuth client JSON` |
| No secret material in the config directory (research R17 secret-scan guard) | `config dir contains secret-like file templates/client_secret.json; secrets belong in credentials, not the config repo` |
| `backup.keep` ≥ 1; `backup.dir` absolute | |
| `calendar.url` must be `https://` | |
| `youtube.channel_handle` must start with `@` | `youtube.channel_handle: must look like @handle` |
