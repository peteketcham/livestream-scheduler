# Contract: CLI Additions (extends 001 [cli.md](../../001-youtube-livestream-scheduler/contracts/cli.md))

Exit codes and the global options are unchanged.

## `preview [<occurrence-id> | --date YYYY-MM-DD] [--next N=3]`

Renders the title and description exactly as they would be published. It contacts no one, apart from an optional lectionary refresh when the cache is stale (`--offline` disables that). Output for each occurrence:
- the title and description, with a character/byte count against the limits
- the template names used
- every `service.*` value with its source (`computed` / `site <url> @ <fetched_at>` / `override`)
- any warnings

This covers 002 US3-1, 003 US1-6, and SC-004/SC-006 of 002/003.

## `templates check`

Validates all configured and bundled templates (research T1, contracts/template-values.md). Prints `ok` or `file:line: message`. Exits 2 on any error. `config check` (001) also runs this.

## `lectionary show <YYYY-MM-DD>`

Shows the computed day for that date: name, year, season, and special names. It also shows the cached site values (readings, color, series, week, URL, fetched time, `valid`/`invalid` with reason), plus the site export's name for the date and whether it matches.

## `lectionary refresh [--date YYYY-MM-DD]`

Forces a fetch now, still within the etiquette limits in research L5, and reports what changed.

## Run records

`run_item.action` gains `lectionary_pending` (an occurrence waiting for site-only values) and `lectionary_invalid`. `status` lists the services waiting for lectionary data.

## Notification problem keys

`lectionary:fetch` (site unreachable or robots-disallowed), `lectionary:invalid:<date>`, `lectionary:mismatch:<date>`, and `template:<name>` (template error). All follow 001 R10 deduplication.
