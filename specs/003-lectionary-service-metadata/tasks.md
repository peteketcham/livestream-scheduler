---
description: "Task list for 003 Lectionary-Based Titles and Descriptions"
---

# Tasks: Lectionary-Based Titles and Descriptions for Church Services (003)

**Input**: `specs/003-lectionary-service-metadata/`: plan.md, spec.md (with amendments 1–4), research.md (L1–L10), data-model.md, contracts/ (liturgical-calendar, template-values, default-templates, config-additions, cli-additions), reference/ (golden examples + captures), quickstart.md

**Prerequisites**: [001 tasks](../001-youtube-livestream-scheduler/tasks.md) Phases 1–4 and [002 tasks](../002-description-templates/tasks.md) Phases 1–4.

**Cross-feature note**: following the [004 plan](../004-taize-funeral-services/plan.md) delivery order, this file builds the **service-type registry core with the `worship` type**, using the `service_type` column instead of 003's `is_service`. It also builds the **three-part footer**. 004 then adds Taizé and funeral types without rework. Migration file: `0003_lectionary_service_types.sql`.

**Tests**: INCLUDED (test-first; golden and oracle tests are central). **Commits**: Conventional Commits with scopes `liturgy`, `lectionary`, `service-types`, `templating`.

## Format: `[ID] [P?] [Story] Description`

[Story] = US1/US2/US3 from `specs/003-lectionary-service-metadata/spec.md`.

---

## Phase 1: Setup

- [ ] T001 Run `uv add "beautifulsoup4>=4.12,<5"` and commit `pyproject.toml` and `uv.lock`
- [ ] T002 [P] Copy the captures into test fixtures:
  - `reference/captures/umc-lectionary-export-2026-10-08.ics` → `tests/fixtures/lectionary/umc-2019-2026.ics`
  - `lectionary-listing-2026-10-08.html` → `tests/fixtures/lectionary/listing-2026-10-08.html`
  - `planning-2026-10-18.html` → `tests/fixtures/lectionary/planning-2026-10-18.html`
- [ ] T003 [P] Create `tests/fixtures/reference/` with exact expected text files built from `reference/sunday-examples.md`:
  - `2026-09-27.title.txt`, `2026-09-27.description.txt`, `2026-10-04.title.txt`, `2026-10-04.description.txt`
  - preserve the double space after "you." and the trailing space after "available at:"
  - in the Oct 4 description, "nineteenth" becomes "Nineteenth", the one documented normalization
- [ ] T004 [P] Create the empty packages `src/livestream_scheduler/liturgy/`, `src/livestream_scheduler/lectionary/`, `src/livestream_scheduler/service_types/` and the test dirs `tests/unit/liturgy/`, `tests/unit/lectionary/`, `tests/unit/service_types/`

---

## Phase 2: Foundational (Blocking Prerequisites)

### Tests first

- [ ] T005 [P] Write `tests/unit/liturgy/test_calendar_examples.py` with every row of the "Verification" table in contracts/liturgical-calendar.md:
  - 2026-09-27 Eighteenth…; 2026-10-04 Nineteenth…; 2026-10-18 Twenty-First…; 2026-11-01 Twenty-Third…; 2026-11-22 Twenty-Sixth…
  - 2026-11-29 First Sunday of Advent, B; 2026-12-24 Christmas Eve, B; 2026-04-05 Easter Sunday, A
  - 2026-05-24 → alias Pentecost; 2026-05-31 → alias First Sunday after Pentecost
  - 2023-12-24 09:30 → Fourth Sunday of Advent and 18:00 → Christmas Eve
  - plus Easter dates 2019–2030 checked against a known table
- [ ] T006 [P] Write `tests/unit/liturgy/test_oracle.py`: parse `tests/fixtures/lectionary/umc-2019-2026.ics`, normalize (casefold, strip `, Year X`, `after the Epiphany`→`after Epiphany`, `After Christmas Day`→`after Christmas`) and compare against the computed name and year. Allow only the entries in an explicit `KNOWN_DIVERGENCES` dict in the test file: the 36 special-name and wording variants listed in research L1 / the prototype output. Any new divergence fails.
- [ ] T007 [P] Write `tests/unit/liturgy/test_special_days.py`: defaults give 2026-11-01 → `["All Saints Sunday"]` and 2026-11-22 → `["Reign of Christ / Christ the King Sunday"]`; 2026-10-04 → `[]` (World Communion **not** default). Cover each rule kind (`first_sunday_of`, `nth_sunday`, `sunday_before: advent`, `fixed`, `easter_offset`, `pentecost_offset`).
- [ ] T008 [P] Write `tests/unit/service_types/test_classify_worship.py` (003 clarification 1, 004 S1):
  - Sunday 09:30 → `worship (rule)`; Sunday 12:00 → `other`
  - `yt.service: yes` on a Friday → `worship (directive)`; `yt.service: no` on Sunday 09:30 → `other`
  - a directive on the series master applies to its instances; an instance directive wins
  - Saturday 17:00 with `yt.service: yes` → service date = next Sunday

### Implementation

- [ ] T009 Implement `src/livestream_scheduler/liturgy/calendar.py` per contracts/liturgical-calendar.md:
  - Gregorian computus; anchors; the Names table exactly, including ordinal words First…Twenty-Eighth hyphenated from Twenty-First
  - the Epiphany window Jan 2–6 and the Baptism window Jan 7–13
  - Sundays after Pentecost: n = weeks since P, with Trinity as First
  - the Dec 24 Sunday split at 16:00
  - year letter `"ABC"[advent_year % 3]`, season and default color
  - `liturgical_day(date, local_time=None) -> LiturgicalDay | None`
- [ ] T010 [P] Implement `src/livestream_scheduler/liturgy/special_days.py`: rule evaluation for the six rule kinds and the defaults
- [ ] T011 Implement `src/livestream_scheduler/service_types/registry.py` (core):
  - load `service_types` from config with the bundled default for `worship` only: `match.when {weekday: sunday, before: "12:00"}`, `saturday_vigil_after: "16:00"`, `lectionary: true`, `title_template: [service-title, service-title-no-special]`, `description_template: service-description`, `visibility: public`, `default_duration_minutes: 75`
  - `other` is implicit
  - validate unique ids and that referenced templates exist
- [ ] T012 Implement `src/livestream_scheduler/service_types/classify.py`: precedence directive (`yt.type`, alias `yt.service: yes|no`) > keyword (NFKD + casefold + whole word; no keyword types yet) > rule > `other`. Returns `(type_id, reason)`.
- [ ] T013 Extend `src/livestream_scheduler/config.py` with `service.church_name` (default `Minnehaha United Methodist Church`), `service.no_article_names` (default list in contracts/config-additions.md incl. `Pentecost`) and the `lectionary.*` block:
  - `enabled`, `listing_url` (must be `https://www.umcdiscipleship.org/…`), `special_days`
  - `name_aliases` (defaults `Day of Pentecost`→`Pentecost`, `Trinity Sunday`→`First Sunday after Pentecost`)
  - `use_site_special_names: false`, `allow_prose: false`, `contact: null`, `refresh_hours: 24`
- [ ] T014 Write `db/schema/0003_lectionary_service_types.sql`:
  - `occurrence.service_type TEXT NOT NULL DEFAULT 'other'`, `occurrence.type_reason TEXT NOT NULL DEFAULT 'default'`, `occurrence.service_date TEXT NULL`, `occurrence.awaiting_site_data INTEGER NOT NULL DEFAULT 0`
  - the `lectionary_day` table (all fields in data-model.md; `status` in `unknown|listed|valid|invalid|unavailable`; `last_good_at`)
  - the `lectionary_source` table (`CHECK (id = 1)`)

**Checkpoint**: The liturgy oracle passes. Classification is unit-tested.

---

## Phase 3: User Story 1 - Liturgical day in title and description (Priority: P1) 🎯 MVP

**Goal**: Sunday-morning services get `October 18th, 2026 - Twenty-First Sunday after Pentecost` and the church's exact description, with no site fetching needed.

**Independent Test**: Golden renders for Sept 27 and Oct 4, 2026 match the reference byte-for-byte (SC-001a). The Oct 18, Nov 1, Nov 22, May 24 and Easter-with-suffix renders match contracts/default-templates.md.

### Tests for User Story 1 ⚠️

- [ ] T015 [P] [US1] Write `tests/integration/test_golden_sundays.py`: render 2026-09-27 and 2026-10-04 Sunday 09:30 occurrences with the bundled templates and compare to `tests/fixtures/reference/*.txt` byte-for-byte (SC-001a)
- [ ] T016 [P] [US1] Write `tests/integration/test_default_templates.py` with every row of the "Expected renders" table in contracts/default-templates.md:
  - Nov 1 `(All Saints Sunday)`
  - Nov 22, a 100-char title kept whole
  - Nov 22 with a longer special name → falls back to `service-title-no-special` with a warning
  - May 24 `for Pentecost!` (no article)
  - `yt.title-suffix: with the band` → `April 5th, 2026 - Easter Sunday with the band`
  - Christmas Eve, no article
- [ ] T017 [P] [US1] Write `tests/integration/test_us1_acceptance_003.py`: US1-4 (a non-service event is unchanged) and US1-6 (`preview` lists `service.*` values with their source `computed`)

### Implementation for User Story 1

- [ ] T018 [P] [US1] Add the bundled snippets under `src/livestream_scheduler/defaults/templates/snippets/`: `bulletin.txt.j2`, `links.txt.j2` (trailing space after `at:`), `licensing.txt.j2` and `minnehaha-footer.txt.j2`, the exact text in [004 contracts/templates.md § Footer parts](../004-taize-funeral-services/contracts/templates.md#footer-parts-s7)
- [ ] T019 [P] [US1] Add `src/livestream_scheduler/defaults/templates/service-title.txt.j2` (`{{ date_long }} - {{ service.label }}{% if title_suffix %} {{ title_suffix }}{% endif %}`), `service-title-no-special.txt.j2` (the same with `service.day_name` instead of `service.label`) and `service-description.txt.j2` (`Welcome to {{ service.church_name }} on {{ date_long }} for {{ service.article }}{{ service.label }}!`, a blank line, then the footer include), per contracts/default-templates.md
- [ ] T020 [US1] Implement `src/livestream_scheduler/service.py`: `service_context(occurrence, type, config, lectionary_store | None) -> dict | None`
  - `None` unless the type has `lectionary: true`
  - computed `day_name` (after `name_aliases`), `special_names`, `label`, `article` (`""` for `no_article_names`, else `"the "`), `year`, `season`, `color` (computed default for now), `church_name`
  - applies the Saturday-vigil date
  - site-only values (`readings`, `series_title`, `week_title`, `planning_url`) are `none` until US2
- [ ] T021 [US1] Wire classification and the service context into `src/livestream_scheduler/sync/run.py` and `templating/render.py`:
  - classify → store `service_type` and `type_reason`
  - templates chosen from the type's registry entry (002 T019 hook)
  - `context["service"] = service_context(...)`
  - snapshot `values_json`
- [ ] T022 [US1] Extend `preview` in `src/livestream_scheduler/cli.py` to print the service type, the reason, and each `service.*` value with its source (`computed`/`site`/`override`)

**Checkpoint**: The user's core request works offline. Deploying here is valid (plan delivery step 3).

---

## Phase 4: User Story 2 - Lectionary details from the site (Priority: P2)

**Goal**: Readings, color, series and week title, and the planning link, from umcdiscipleship.org, polite and validated, with the last good values never lost.

**Independent Test**: With fixtures served by `responses`, `lectionary show 2026-10-18` lists Exodus 33:12-23; Psalm 99; 1 Thessalonians 1:1-10; Matthew 22:15-22, Green, "Always Give Thanks"/"Chosen". Mutated fixtures → `invalid` with the previous values kept.

### Tests for User Story 2 ⚠️

- [ ] T023 [P] [US2] Write `tests/unit/lectionary/test_planning_page.py`:
  - the 2026-10-18 fixture → the 4 references, `Green`, week `Chosen`, series `Always Give Thanks`, date 2026-10-18
  - mutated copies → `invalid`: References removed (`no References section`), date changed (`page date 2026-10-17 ≠ 2026-10-18`), color `Teal` (`unknown color`)
- [ ] T024 [P] [US2] Write `tests/unit/lectionary/test_listing.py`: the listing fixture gives a date → planning URL map, including 2026-10-18 and 2026-10-25, and the export URL discovered from the "Export Events" link
- [ ] T025 [P] [US2] Write `tests/unit/lectionary/test_fetch_policy.py` (research L5):
  - ≤1 fetch per page per 24 h; conditional headers sent
  - a 1 s gap between requests; User-Agent `livestream-scheduler/<version> (+<repo url>)` with no email unless `lectionary.contact`
  - a robots.txt disallow → the path is not fetched and `lectionary:fetch` is raised
- [ ] T026 [P] [US2] Write `tests/integration/test_lectionary_outage.py` (FR-008, SC-005): `valid` data, then the site returns 500 or an invalid page → published text unchanged, `last_good_at` unchanged, and one notification
- [ ] T027 [P] [US2] Write `tests/integration/test_awaiting_site_data.py` (FR-006): a template using `service.readings` for a date not yet listed → created with the "only if present" section omitted and `awaiting_site_data=1`. When the data appears → one update.

### Implementation for User Story 2

- [ ] T028 [P] [US2] Implement `src/livestream_scheduler/lectionary/fetch.py`: a `requests.Session` with the User-Agent per L5, a robots.txt check (cached 24 h), conditional GET, a 15 s timeout, sequential requests with a 1 s spacing, and per-URL 24 h refresh using `lectionary_source`/`lectionary_day` timestamps
- [ ] T029 [P] [US2] Implement `src/livestream_scheduler/lectionary/listing.py`: parse the listing page (BeautifulSoup `html.parser`) into `{date: planning_url}` and discover the export URL
- [ ] T030 [P] [US2] Implement `src/livestream_scheduler/lectionary/planning_page.py`:
  - extract the date, `<h3>References</h3>` list items, `div.colors` text, and the week and series titles
  - validate the date equals the requested date, ≥1 reference matches `^(?:[1-3] )?[A-Z][a-z]+(?: [A-Z][a-z]+)* \d+(?::\d+(?:[-–]\d+)?)?`, and the color is in {Green, White, Purple, Blue, Red, Gold, Black, Rose}
  - skip prose unless `allow_prose`
- [ ] T031 [P] [US2] Implement `src/livestream_scheduler/lectionary/export.py` (L4): parse the export ICS. A name mismatch is recorded only. A year-letter mismatch, or a missing Sunday, → a warning and notification `lectionary:mismatch:<date>`.
- [ ] T032 [US2] Implement `src/livestream_scheduler/lectionary/store.py`: upsert `lectionary_day`, keeping the transitions in data-model.md. **Never overwrite valid values with an invalid or failed fetch.** `last_good_at` only moves on `valid`.
- [ ] T033 [US2] Extend `src/livestream_scheduler/service.py` with the site values (`readings`, `color` overriding the computed default, `series_title`, `week_title`, `planning_url`, `site_data`; `summary`/`credit` only with `allow_prose`) and set `occurrence.awaiting_site_data` when templates reference missing site-only values
- [ ] T034 [US2] Call the lectionary refresh in `src/livestream_scheduler/sync/run.py` before rendering, for service dates within the horizon. A failure never aborts scheduling.
- [ ] T035 [US2] Add the CLI commands `lectionary show <date>` and `lectionary refresh [--date]` to `src/livestream_scheduler/cli.py` (contracts/cli-additions.md), and the run_item actions `lectionary_pending` and `lectionary_invalid`

---

## Phase 5: User Story 3 - Owner overrides for a specific service (Priority: P3)

**Goal**: Per-event directives override any lectionary value or the whole title.

**Independent Test**: One instance with `yt.readings: Psalm 23` and `yt.title: Guest Preacher Sunday` → only that instance changes, and preview shows the source `override`.

### Tests for User Story 3 ⚠️

- [ ] T036 [P] [US3] Write `tests/integration/test_overrides.py`: US3-1 (readings override; other values unchanged), US3-2 (full title override is verbatim), and `yt.day-name`, `yt.special` (empty clears), `yt.series`, `yt.week-title`

### Implementation for User Story 3

- [ ] T037 [US3] Implement the override precedence (directive > site > computed) in `src/livestream_scheduler/service.py` for `yt.day-name`, `yt.special` (`;`-list), `yt.readings` (`;`-list), `yt.series`, `yt.week-title`, recording `source=override` per value in `values_json`

---

## Phase 6: Polish

- [ ] T038 [P] Document in `README.md`: Sunday detection, special days, name aliases, the `yt.*` directives for services, and how to add observances (e.g. Laity Sunday)
- [ ] T039 Run quickstart.md (003) manual scenarios 1–10 on the test channel. `uv run pytest` passes in full.

---

## Dependencies & Execution Order

- 001 (1–4) + 002 (1–4) → T001–T004 → T005–T014 → **US1 T015–T022 (shippable)** → US2 T023–T035 → US3 T036–T037 → Polish.
- US3 only needs US1 (overrides of computed values). Overrides of site values need US2.

## Parallel Opportunities

- T002–T004. Tests T005–T008. T009 and T010. T015–T017. T018 and T019. US2 tests T023–T027, then T028–T031.

## Implementation Strategy

Ship **US1** first (computed names and exact Minnehaha format). It fully solves the weekly retyping chore without depending on the external site. Add US2 (site values) when readings or series are wanted in templates. Then go to [004 tasks](../004-taize-funeral-services/tasks.md).
