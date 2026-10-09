# Phase 0 Research: Lectionary-Based Titles and Descriptions

**Feature**: `003-lectionary-service-metadata` | **Date**: 2026-10-08

This plan builds on [001's research](../001-youtube-livestream-scheduler/research.md) (R1–R15). It also **designs the template engine from [002](../002-description-templates/spec.md)**, which has no plan of its own: 003's title templates and default Minnehaha templates cannot be designed without it. Decisions here are numbered **T** (templating, covering 002) and **L** (lectionary, covering 003).

Inputs examined on 2026-10-08:
- the lectionary listing page
- its calendar export (ICS, 412 entries, 2019-10-06 → 2026-12-27)
- the Oct 18, 2026 planning page
- the Special Sundays calendar
- `robots.txt`
- two reference livestreams ([reference/sunday-examples.md](reference/sunday-examples.md))

---

## T1. Template language and sandbox (002 FR-001, FR-005, FR-007, FR-008, FR-015)

- **Decision**: Use **Jinja2 3.1** with `jinja2.sandbox.SandboxedEnvironment`:
  - `undefined=StrictUndefined`. A misspelled placeholder raises an error and is never rendered blank (002 FR-008).
  - `FileSystemLoader(<templates_dir>)` only. Jinja's loader rejects `..` and absolute paths, so includes cannot leave the folder (002 FR-015).
  - `autoescape=False`, because the output is plain text, not HTML.
  - `keep_trailing_newline=True`, `trim_blocks=True`, `lstrip_blocks=True`.
  - No extensions and no globals except the filters in T3.
  - Templates never receive the config object, environment variables, or tokens. The template context is built from an explicit allowlist ([contracts/template-values.md](contracts/template-values.md)).
- **Rationale**: The owner suggested Jinja. The sandbox blocks attribute-walking escapes. StrictUndefined turns typos into visible errors. Snippets work through the built-in `{% include %}`.
- **Alternatives considered**: `string.Template` was too weak (no conditionals, loops or includes). Liquid (`python-liquid`) would be equally safe but is less familiar to the owner, who named Jinja.

## T2. Plain text vs. Markdown templates (002 FR-006)

- **Decision**: The template file extension selects the output pipeline:
  - **`.txt.j2`**: the rendered text is published as-is (apart from limits, T4). Whitespace and line breaks are preserved exactly.
  - **`.md.j2`**: the rendered Markdown is parsed by **markdown-it-py** with `breaks=True` and converted to plain text by a small custom renderer:
    - headings become their own line
    - list items become `• ` or `1. `
    - `[text](url)` becomes `text: url`, or just `url` when the text equals the URL
    - emphasis markers are dropped
    - paragraphs are separated by a blank line
- **Rationale**: The church's reference descriptions depend on exact single-line breaks, a double space after "you.", and a trailing space after "at:". Standard Markdown would merge lines into paragraphs and break the golden-output criterion (003 SC-001a). The **default Minnehaha templates are therefore `.txt.j2`**, while owners who want headings and lists can still use Markdown.
- **Values inserted into `.md.j2`** (calendar notes, readings) are escaped for Markdown by a `md` autoescape filter applied to every value, so a `*` in a calendar note cannot turn text italic.

## T3. Dates and ordinals (002 FR-004)

- **Decision**:
  - Filters: `ordinal` (`4` → `4th`, `1` → `1st`, `22` → `22nd`, `13` → `13th`), `strftime(fmt)`, and `date_long`. `date_long` renders `October 4th, 2026` (month name, ordinal day, comma, year) in the occurrence's time zone.
  - Pre-computed values: `start_local`, `end_local`, `date_long`, `time_short` (`9:30 AM`).
  - Month names are always English (no locale dependence). Output never depends on the host locale or the current time (002 FR-016).
- **Rationale**: Both reference titles use `October 4th, 2026` / `September 27th, 2026`, and `strftime` has no ordinal directive.

## T4. Limits after rendering (002 FR-009)

- **Decision**:
  - **Title**: maximum 100 characters. If the service label's parenthetical makes the title too long, the parenthetical is dropped first (003 clarification). Otherwise the title is cut at the last word boundary and `…` is appended. Each step adds a warning.
  - **Description**: maximum 5000 UTF-8 bytes. It is cut at the last blank line, then the last line break, then the last word that fits, with a warning.
  - **Both**: `<` and `>` are removed, with a warning.
  - **Line endings**: normalized to `\n`.
- **Rationale**: These are YouTube's limits, the same as 001 R3.

## T5. Change detection and determinism (002 FR-012, FR-016; 001 R6)

- **Decision**: The occurrence's `desired_hash` (001 data model) is computed over the **rendered** title and description plus privacy and times. Any change to a template, snippet, variable, lectionary value, or calendar event therefore changes the hash and leads to one update. No change means no update. Rendering is pure: there is no clock, no randomness, and dict iteration is sorted. A property test renders each fixture twice and compares the results.
- **Rationale**: This reuses 001's update and manual-edit machinery unchanged (002 FR-013).

## T6. Template selection (002 FR-002, FR-003; 003 FR-004/005)

- **Decision**: Templates are selected in this order:
  1. Per-event directive `yt.template: <name>` (description) / `yt.title-template: <name>`.
  2. **Church services** → `service.description_template` / `service.title_template` from config. The defaults are the bundled Minnehaha templates.
  3. `templates.default_description` / `templates.default_title`.
  4. If none applies: no template. The title is the calendar `SUMMARY` and the description is the notes (002 FR-014).

  Full per-event overrides: `yt.title: <text>` is used verbatim, and `yt.description: verbatim` uses the calendar notes as-is, skipping the template.

---

## L1. Source of the liturgical day name (003 FR-002, amended)

**Finding**: The site's calendar export is internally inconsistent across years. Taken from the 2019–2026 export:

| Date | Site name |
|---|---|
| 2020-11-01 | `All Saints Day, Year A` |
| 2023-11-05 | `All Saints Sunday, Year A` |
| 2026-11-01 | `Twenty-Third Sunday after Pentecost, Year A` (not yet renamed) |
| 2019-11-24 | `Reign of Christ, Christ the King Sunday, Year C` |
| 2025-11-23 | `Christ the King / Reign of Christ, Year C` |
| 2026-11-22 | `Twenty-Sixth Sunday after Pentecost, Year A` |
| 2020-06-14 | `Second Sunday After Pentecost` (capital "After") |
| 2024-09-15 | `…, year B` (lower-case) |
| 2026-04-05 | `Easter Sunday 2026, Year A` |

The listing page also showed the same Sunday under two dates ("Week 4 – Twentieth Sunday…" under Oct 11 and Oct 17).

- **Decision**: **Work out the day name, year letter, and season locally** from the Revised Common Lectionary calendar rules:
  - Easter is computed with the Gregorian computus. Advent 1 is the fourth Sunday before Dec 25.
  - The year letter is A/B/C by the calendar year in which Advent 1 falls (`year % 3`: 0 → A, 1 → B, 2 → C).
  - Sundays after Pentecost are counted from the Day of Pentecost, so Trinity Sunday is the first.

  The naming table and rules are in [contracts/liturgical-calendar.md](contracts/liturgical-calendar.md). The site export is used only as a **cross-check** (L4).
- **Rationale**:
  - Titles are deterministic, always available (even beyond the site's horizon), consistently capitalized, and never churn when the site renames a day.
  - Verified by hand: Oct 4, 2026 is 19 Sundays after Pentecost (May 24, 2026), giving "Nineteenth" ✓. Sept 27 gives "Eighteenth" ✓. Oct 18 gives "Twenty-First" ✓. Nov 29, 2026 is Advent 1, Year B ✓ (the site agrees).
  - The full 2019–2026 export is kept as a **test oracle** (`tests/fixtures/lectionary/umc-2019-2026.ics`). Every entry must equal our computed name after normalization (capitalization and `, Year X` removed), or be listed in the oracle's known-divergence table (special names, "Easter Sunday 2026", Holy Week extras such as Las Posadas or Blue Christmas).
- **Alternatives considered**:
  - Using the site's names directly was rejected: inconsistent, renamed late, and only ~11 weeks ahead.
  - A static name table per date was rejected: it needs yearly maintenance.

## L2. Special-day names (003 clarification: "label (special)")

- **Finding**: The site's Special Sundays calendar returns "No events … today until 6 months from today". Special names only appear sometimes, *in place of* the numbered name, in the main export.
- **Decision**: Use an **owner-editable list of observed special days** in config, each with a name and a date rule:
  - `first_sunday_of: november`
  - `sunday_before: advent`
  - `nth_sunday: {month: october, n: 1}`
  - `fixed: 12-24`
  - `easter_offset: -7`

  Defaults:

  | Name | Rule |
  |---|---|
  | All Saints Sunday | first Sunday of November |
  | Reign of Christ / Christ the King Sunday | Sunday before Advent |

  **World Communion Sunday is not a default**, because the church titled Oct 4, 2026 (the first Sunday in October) as `Nineteenth Sunday after Pentecost` with no parenthetical, and SC-001a requires that output. Site-provided special names are ignored by default. `lectionary.use_site_special_names: true` turns them on when the site's name normalizes to something other than our computed name.
- **Rationale**: This is deterministic, matches the church's observed practice, and lets the owner add observances (e.g. Laity Sunday) with one config line.

## L3. Where readings, color, series, and links come from (003 FR-002)

**Finding**: Readings and color are not in the export. Planning pages carry them under stable markup: `<h3>References</h3>` followed by a list of references, and `<div class="colors">` with the color name. The week and series titles are in the page header. The listing page (`/calendar/lectionary`) links the planning page for each upcoming date, about 5 weeks ahead.

- **Decision**:
  1. Fetch the listing page and collect a map from date to planning-page URL, using the page's date heading.
  2. For each **service date within the horizon**, fetch its planning page, parse it with **BeautifulSoup** (`html.parser`, no lxml dependency), and extract the date, references, color, week title, and series title.
  3. **Validate** (003 FR-012):
     - the page's own date must equal the service date (this resolves the "two dates" discrepancy)
     - there must be at least one reference matching a scripture-reference pattern (`^(?:[1-3] )?[A-Z][a-z]+(?: [A-Z][a-z]+)* \d+(?::\d+(?:[-–]\d+)?)?`)
     - the color must be in {Green, White, Purple, Blue, Red, Gold, Black, Rose}

     Anything else marks the data `invalid`. It is not used, and the owner is notified once.
  4. Store results per date. Last-good values are **never** overwritten by a failed or invalid fetch (003 FR-008).
- **Alternatives considered**: Computing readings from a local Revised Common Lectionary table would work offline, but the reading table is the Consultation on Common Texts' copyrighted compilation, and the site is the source the owner named. This can be revisited.

## L4. Cross-check with the site export (003 edge cases)

- **Decision**: Once a day, fetch the export (the URL is discovered from the listing page's "Export Events" link, with a fallback to the last known URL) and compare each in-horizon date's normalized name and year letter with ours:
  - Name differs: info only. Recorded in `lectionary_day.site_name`, shown by `lectionary show`.
  - **Year letter differs, or a date that we name as a Sunday is missing**: a warning plus one notification (`problem_key=lectionary:mismatch:<date>`).

## L5. Fetch etiquette (003 FR-009)

- **Decision**:
  - Requests:
    - the listing page and the export: each at most once per 24 h
    - each planning page: at most once per 24 h while it is in the horizon
    - dates still missing data: at most once per run (hourly)
  - Use conditional requests (`If-None-Match` / `If-Modified-Since`), a 15 s timeout, sequential requests, and a 1 s gap between requests.
  - `User-Agent: livestream-scheduler/<version> (+<repo url>)`. The owner's email is **not** sent. An optional `lectionary.contact` is appended only if the owner sets it.
  - `robots.txt` (checked 2026-10-08) allows `/calendar/` and `/worship-planning/`. It is re-checked daily, and if it disallows a path, that path is not fetched.
- **Volume**: about 4 planning pages + 2 index requests per day, which is negligible.

## L6. Copyright posture (003 FR-010)

- **Decision**:
  - The values exposed by default are facts: day names, references, color, series and week titles, and the URL.
  - The prose theme summary is **not even parsed** unless `lectionary.allow_prose: true` is set. When it is, templates get `service.summary` plus a required `service.credit` line ("Worship planning content © Discipleship Ministries, umcdiscipleship.org"). Template validation fails if `service.summary` is used without `service.credit`.

## L7. Church-service detection (003 clarification 1, FR-001)

- **Decision**: An occurrence is a service when its local start is on a Sunday and before `service.sunday_cutoff` (default `12:00`), **or** it has the directive `yt.service: yes`. A `yt.service: no` directive always excludes it. A directive on a series master applies to all of its instances, and an instance override wins over the master.
  - **Saturday rule**: a service starting Saturday at or after `service.saturday_vigil_after` (default `16:00`) uses the following Sunday's values.
  - **Other weekdays**: use that date's computed day (Christmas Eve, Ash Wednesday, Maundy Thursday, Good Friday). If the date has no name, the day name is absent and templates fall back.

## L8. Per-event overrides (003 FR-007)

- **Decision**: These directives are lines in the calendar notes. They are removed from published text, as in 001 R3:

  | Directive | Overrides |
  |---|---|
  | `yt.day-name` | `service.day_name` |
  | `yt.special` | `service.special_names` (`;`-separated, empty = none) |
  | `yt.readings` | `service.readings` (`;`-separated) |
  | `yt.series` | `service.series_title` |
  | `yt.week-title` | `service.week_title` |
  | `yt.title` | the whole title |
  | `yt.description: verbatim` | the whole description |
  | `yt.var.<name>` | `vars.<name>` |

  Overrides apply after the site values and before rendering. Whatever was overridden is listed in the preview.

## L9. Libraries added

| Concern | Choice |
|---|---|
| Templates | `Jinja2` 3.1 (sandboxed) |
| Markdown → text | `markdown-it-py` 3.x |
| HTML parsing | `beautifulsoup4` 4.12 (stdlib `html.parser`) |
| ICS (export cross-check) | `icalendar` (already a dependency in 001) |

## L10. Testing strategy additions

- **Golden tests** (SC-001a): render Sept 27 and Oct 4, 2026 with the default templates and compare byte-for-byte with `reference/sunday-examples.md`, after applying the single documented normalization (capitalized day name in the welcome line).
- **Oracle test** (L1): every Sunday and named day in the 2019–2026 export normalizes to our computed name, or is in the known-divergence table.
- **Parser fixtures**: saved HTML of the Oct 18, 2026 planning page and listing page, plus mutated copies (missing References, wrong date, unknown color) that must yield `invalid`.
- **Sandbox tests**: `{{ ''.__class__ }}`-style escapes, `{% include '../x' %}`, and a misspelled variable must all fail validation.
- **Determinism**: render twice → identical output. Twenty consecutive syncs with nothing changed → 0 updates.
