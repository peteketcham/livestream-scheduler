# Data Model: Templates and Lectionary (extends 001 [data-model.md](../001-youtube-livestream-scheduler/data-model.md))

Templates are files, not database rows. The additions below are SQLite tables and columns.

**Migrations** (numbered in feature build order; see the tasks lists):
- `0002_templates.sql` (002): `title_template`, `description_template`, `render_warnings`, `values_json`
- `0003_lectionary_service_types.sql` (003): `service_type`, `type_reason`, `service_date`, `awaiting_site_data`, plus `lectionary_day` and `lectionary_source`

There is no `is_service` column. 003 uses 004's `service_type` from the start, with the `worship` type.

## occurrence (new columns)

| Field | Type | Rules |
|---|---|---|
| service_type | TEXT NOT NULL DEFAULT 'other' | Registry id; `worship` = church service per research L7 (004 [service-types](../004-taize-funeral-services/contracts/service-types.md)) |
| type_reason | TEXT NOT NULL DEFAULT 'default' | `directive` \| `keyword` \| `rule` \| `default` |
| service_date | TEXT NULL | The lectionary date used. This is the next day for Saturday-vigil services. |
| title_template | TEXT NULL | Name used. NULL means none (calendar SUMMARY). |
| description_template | TEXT NULL | |
| render_warnings | TEXT NULL | JSON list. Truncation, removed characters, dropped parenthetical. |
| values_json | TEXT NULL | Snapshot of the template context used (no secrets), for `preview` and audit (003 FR-011) |
| awaiting_site_data | INTEGER (0/1) NOT NULL DEFAULT 0 | 1 when the templates reference site-only values that are missing (003 FR-006) |

**Rule change**: `title` and `description` now hold the **rendered** text, and `desired_hash` covers that rendered text (research T5). When rendering fails (any template error), the occurrence becomes `failed` with `state_reason = "Template <name>: <file:line message>"`. An already-`scheduled` occurrence **stays scheduled with its last published text**: nothing is pushed, and the problem is recorded (002 FR-008, edge case "syntax error").

## lectionary_day

Holds one row per date that has been requested.

| Field | Type | Rules |
|---|---|---|
| date | TEXT PK | `YYYY-MM-DD` |
| computed_name / year / season / default_color | TEXT NOT NULL | From `liturgy.calendar`. Recomputed on read and stored for audit. |
| site_name | TEXT NULL | The export's SUMMARY, raw |
| site_name_matches | INTEGER NULL | After normalization (research L4) |
| site_year | TEXT NULL | |
| planning_url | TEXT NULL | From the listing page |
| readings_json | TEXT NULL | Ordered list of references |
| color | TEXT NULL | From the planning page |
| series_title / week_title | TEXT NULL | |
| summary | TEXT NULL | Stored only if `allow_prose` |
| status | TEXT NOT NULL | `unknown` \| `listed` (URL known, page not fetched) \| `valid` \| `invalid` \| `unavailable` |
| status_reason | TEXT NULL | e.g. `page date 2026-10-17 ≠ 2026-10-18`, `no References section` |
| last_good_at | TEXT NULL | Time of the last `valid` fetch. Its values are never overwritten by a non-valid fetch (003 FR-008). |
| fetched_at | TEXT NULL | Last attempt |
| etag / last_modified | TEXT NULL | Conditional requests |

**Transitions**:
- `unknown` → `listed` when the listing page provides a URL.
- `listed` → `valid` or `invalid` after the planning page is fetched.
- `valid` → `valid` on refresh. If a refresh comes back `invalid`, the previous valid values are kept, `status_reason` notes the failed refresh, and the owner is notified.
- `unknown` → `unavailable` when the date is past the listing's range; it is retried each run per research L5.

## lectionary_source

Holds one row (id = 1) with the index fetch state.

| Field | Type | Rules |
|---|---|---|
| listing_fetched_at / listing_etag | TEXT NULL | |
| export_url | TEXT NULL | Discovered from the "Export Events" link |
| export_fetched_at / export_etag | TEXT NULL | |
| robots_fetched_at | TEXT NULL | |
| robots_disallow_json | TEXT NULL | Paths blocked for our User-Agent |

## Entities without tables

- **Description/Title Template, Snippet**: files in `templates.dir` or the bundled defaults (contracts/template-values.md).
- **Observed Special Day**: config `lectionary.special_days` (contracts/config-additions.md).
- **Service Values**: built per render from `lectionary_day`, config, and directives, and snapshotted in `occurrence.values_json`.
