# Livestream configuration (seed)

This repository holds Minnehaha UMC's settings for livestream-scheduler. It contains **no secrets**.

| Path | What it is |
|---|---|
| `config.yaml` | Settings ([schema](https://github.com/peteketcham/livestream-scheduler/blob/main/specs/001-youtube-livestream-scheduler/contracts/config-schema.md)). Secrets are `{credential: …}` references only. |
| `templates/` | Description/title templates that override the bundled defaults (feature 002/003) |

**Deploying a change**: commit and push, then run `sudo deploy/install.sh config-pull` on the server. The new config is validated first and only activated if it passes.

**Never commit** OAuth client JSON, tokens, the calendar's secret address, passwords, or backups. `lss config check` refuses a config directory that contains them. `gitignore.example` lists the patterns, and you can install it as this repository's ignore file.
