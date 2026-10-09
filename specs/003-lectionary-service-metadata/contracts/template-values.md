# Contract: Template Context and Filters

This contract covers feature 002 (all events) and feature 003 (`service.*`). It lists everything a template can see, and nothing else is reachable (research T1). An undefined name is a validation error. Values marked *optional* may be `none`. Templates guard them with `{% if … %}`.

## Event values (feature 002 — every occurrence)

| Name | Type | Example |
|---|---|---|
| `title` | str | Calendar `SUMMARY`, after prefix strip (`Sunday Worship`) |
| `notes` | str | Calendar notes as plain text, directives removed |
| `start_local` / `end_local` | datetime (tz-aware) | 2026-10-18 09:30 America/Chicago |
| `tz` | str | `America/Chicago` |
| `date_long` | str | `October 18th, 2026` |
| `date_short` | str | `Oct 18, 2026` (title fallbacks, 004 S3) |
| `church_name` | str | `Minnehaha United Methodist Church` (global config; the same value as `service.church_name`) |
| `service_type` | str | `worship` \| `taize` \| `funeral` \| `other` \| owner-defined (004) |
| `<type>.*` | mapping | Per-type details, e.g. `funeral.name` (004 [service-types](../../004-taize-funeral-services/contracts/service-types.md)) |
| `time_short` | str | `9:30 AM` |
| `duration_minutes` | int | `75` |
| `visibility` | str | `public` |
| `series_index` | int, *optional* | 1-based position in its recurring series (counts instances from DTSTART, skips EXDATEs). `none` for single events. |
| `vars` | mapping[str, str] | Global `templates.vars` merged with per-event `yt.var.<name>` (event wins) |

## Service values (feature 003 — `service` is `none` unless the occurrence's service type has `lectionary: true`, i.e. `worship`)

| Name | Type | Source | Example (2026-10-18) |
|---|---|---|---|
| `service.church_name` | str | config | `Minnehaha United Methodist Church` |
| `service.day_name` | str | computed ([liturgical-calendar.md](liturgical-calendar.md)) | `Twenty-First Sunday after Pentecost` |
| `service.special_names` | list[str] | owner list | `[]` |
| `service.article` | str | `"the "`, or `""` for names in `service.no_article_names` (see default-templates.md) | `the ` |
| `service.label` | str | `day_name` + ` (` + special names joined with ` / ` + `)` when there are any | `Twenty-First Sunday after Pentecost` |
| `title_suffix` | str, *optional* | `yt.title-suffix` directive | `with the band` |
| `service.year` | str | computed | `A` |
| `service.season` | str | computed | `Season after Pentecost` |
| `service.color` | str | site, else computed default | `Green` |
| `service.readings` | list[str], *optional* | site | `["Exodus 33:12-23", "Psalm 99", "1 Thessalonians 1:1-10", "Matthew 22:15-22"]` |
| `service.series_title` | str, *optional* | site | `Always Give Thanks` |
| `service.week_title` | str, *optional* | site | `Chosen` |
| `service.planning_url` | str, *optional* | site | `https://www.umcdiscipleship.org/worship-planning/always-give-thanks/week-1-…` |
| `service.summary` / `service.credit` | str, *optional* | site; only when `lectionary.allow_prose: true` | |
| `service.site_data` | bool | true when site values are present and valid | `true` |

Precedence for each value: per-event directive > site value > computed value.

## Filters

| Filter | Example | Result |
|---|---|---|
| `ordinal` | `{{ 22 \| ordinal }}` | `22nd` |
| `strftime(fmt)` | `{{ start_local \| strftime('%A') }}` | `Sunday` (English, locale-independent) |
| `date_long` | `{{ start_local \| date_long }}` | `October 18th, 2026` |
| `join_readings(sep='; ')` | `{{ service.readings \| join_readings }}` | `Exodus 33:12-23; Psalm 99; …` |
| `md` | auto-applied in `.md.j2` | escapes Markdown control characters |

## Template files

- Location: `templates.dir` (default `<config_dir>/templates/`). Bundled defaults live inside the package and are used when the folder does not contain a file of the same name.
- Names: `<name>.txt.j2` (verbatim text) or `<name>.md.j2` (Markdown → plain text). Snippets are ordinary templates, conventionally kept under `snippets/`.
- `templates check` / `config check` validates every template by rendering it against fixture contexts (with and without `service`, with and without site data). Errors are reported as `file:line: message`.
