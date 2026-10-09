# Contract: CLI and Notification Additions

This extends [001 cli.md](../../001-youtube-livestream-scheduler/contracts/cli.md) and [003 cli-additions.md](../../003-lectionary-service-metadata/contracts/cli-additions.md). In production every command runs through `lss` ([001 deployment.md](../../001-youtube-livestream-scheduler/contracts/deployment.md)).

## `link (<occurrence-id> | --date YYYY-MM-DD) [--type <id>]`

Prints the watch URL (`https://youtu.be/<broadcast_id>`), the title, the local start time and the visibility. With `--date` and more than one match, it lists them all. It exits 3 when no livestream exists yet, with the reason (pending, waiting for calendar, failed, or `exists_external` with the external link). `--json` gives `{"occurrence_id", "url", "title", "start", "visibility", "state"}`. This covers FR-009.

## `occurrences … [--type <id> ...]`

Adds a filter and a `type` column showing the service type and why it was chosen (`directive`/`keyword`/`rule`/`default`).

## `preview`

Shows the service type, the reason it was chosen, and the `funeral.*` values with their source (directive or title).

## Immediate run (FR-008)

`sudo systemctl start livestream-scheduler.service` runs the timer's unit right away. `lss sync` does the same, holding the same lock. Both are documented and there is no new command.

## Run items and states

- **New occurrence state**: `exists_external`, with `state_reason` set to `A livestream created by hand already exists at <time>: "<title>" <url>`.
- **New run_item actions**: `external_conflict`, `announce`.

## Emails

| Trigger | Subject | Body includes | Dedup key |
|---|---|---|---|
| Funeral livestream created | `[livestream-scheduler] Funeral livestream scheduled: <title>` | watch URL, local date and time, visibility, calendar event title | `announce:<occ>:created:<start_utc>` |
| Announced funeral moved | `… Funeral livestream changed: <title>` | old → new time, URL | `announce:<occ>:changed:<start_utc>` |
| Announced funeral cancelled | `… Funeral livestream removed: <title>` | former time | `announce:<occ>:cancelled` |
| Hand-made livestream blocks a create | `… Already on the channel: <title>` | external title, link, time, the calendar event it matched, "No duplicate was created; nothing was changed." | `external:<occ>` (once) |
| Funeral without a name | `… PROBLEM: Funeral needs a name` | how to fix (`yt.name:` or title "Funeral for <name>") | `occurrence:<occ>:failed` (001 rules) |

Every email goes only to `notify.email_to` (clarification 3).
