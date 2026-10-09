---
description: "Task list for 002 Templated Livestream Descriptions (+ title templates)"
---

# Tasks: Templated Livestream Descriptions (002)

**Input**:
- spec: `specs/002-description-templates/spec.md`
- design (002 has no plan of its own): [003 plan](../003-lectionary-service-metadata/plan.md), [003 research T1–T6](../003-lectionary-service-metadata/research.md), [template-values](../003-lectionary-service-metadata/contracts/template-values.md), [004 research S3](../004-taize-funeral-services/research.md) (title fallback lists)

**Prerequisites**: [001 tasks](../001-youtube-livestream-scheduler/tasks.md) Phases 1–4 complete (the US1 + US2 sync engine).

**Tests**: INCLUDED (test-first baseline). **Commits**: Conventional Commits with scope `templating`. Run everything through `uv run`.

## Format: `[ID] [P?] [Story] Description`

[Story] = US1/US2/US3 from `specs/002-description-templates/spec.md`.

---

## Phase 1: Setup

- [ ] T001 Run `uv add "jinja2>=3.1,<3.2" "markdown-it-py>=3,<4"` and commit the updated `pyproject.toml` and `uv.lock`
- [ ] T002 [P] Create `src/livestream_scheduler/templating/__init__.py`, the empty `src/livestream_scheduler/defaults/templates/` package-data dir (included via hatch config in `pyproject.toml`) and `tests/unit/templating/`

---

## Phase 2: Foundational (Blocking Prerequisites)

### Tests first

- [ ] T003 [P] Write `tests/unit/templating/test_sandbox.py`. Each of these must fail validation with a `file:line: message` error:
  - `{{ ''.__class__.__mro__ }}`
  - `{{ config }}`
  - `{% include '../secret' %}`
  - `{% include '/etc/passwd' %}`
  - an undefined variable `{{ titel }}` (StrictUndefined)
- [ ] T004 [P] Write `tests/unit/templating/test_filters.py`:
  - `ordinal`: 1→1st, 2→2nd, 3→3rd, 4→4th, 11→11th, 12→12th, 13→13th, 21→21st, 22→22nd, 23→23rd
  - `date_long`: 2026-10-04 → `October 4th, 2026`
  - `date_short`: → `Oct 4, 2026`
  - `strftime('%A')`: English under `LC_ALL=de_DE`
  - `time_short`: 09:30 → `9:30 AM`
- [ ] T005 [P] Write `tests/unit/templating/test_limits.py` (003 research T4):
  - a title over 100 chars → cut at a word boundary + `…` + warning
  - a description over 5000 UTF-8 bytes → cut at a blank line, then a line break, then a word, with a warning
  - `<` `>` removed with a warning
  - line endings normalized to `\n`
- [ ] T006 [P] Write `tests/unit/templating/test_plaintext.py` (T2):
  - `.md.j2`: a heading becomes its own line; list items become `• ` / `1. `
  - `[text](url)` → `text: url`, and `[url](url)` → `url`
  - emphasis markers are dropped; single newlines are kept (`breaks=True`)
  - values are md-escaped, so a `*` in notes stays literal
  - `.txt.j2` output is byte-identical to the input, including trailing spaces and double spaces

### Implementation

- [ ] T007 Implement `src/livestream_scheduler/templating/env.py` (T1):
  - `SandboxedEnvironment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True, trim_blocks=True, lstrip_blocks=True)`
  - a `ChoiceLoader([FileSystemLoader(templates.dir), PackageLoader("livestream_scheduler", "defaults/templates")])`
  - no extensions and no globals
- [ ] T008 [P] Implement `src/livestream_scheduler/templating/filters.py`: `ordinal`, `strftime` (English month and day names from fixed tables, never the host locale), `date_long`, `date_short`, `join_readings(sep='; ')` and `md` (escape Markdown control chars)
- [ ] T009 [P] Implement `src/livestream_scheduler/templating/limits.py`: `apply_title_limits(str) -> (str, warnings)` and `apply_description_limits(str) -> (str, warnings)` per T005
- [ ] T010 [P] Implement `src/livestream_scheduler/templating/plaintext.py`: a markdown-it-py renderer to plain text per T006
- [ ] T011 Implement `src/livestream_scheduler/templating/context.py`: `build_context(occurrence, config) -> dict` with **only** the allowlisted names in contracts/template-values.md "Event values":
  - `title`, `notes`, `start_local`, `end_local`, `tz`, `date_long`, `date_short`, `time_short`, `duration_minutes`, `visibility`
  - `series_index` (1-based from DTSTART, skipping EXDATEs; `none` for single events)
  - `vars` (`templates.vars` merged with `yt.var.<name>`; the event wins)
  - `church_name`, `title_suffix` (from `yt.title-suffix`)
  - `service_type` set to `"other"` (003 and 004 extend the context)
- [ ] T012 Extend `src/livestream_scheduler/config.py` with the `templates` block (`dir`, `default_title`, `default_description`, `vars`) and the global `church_name` (contracts/config-additions.md in 003). Add the 002 calendar directives `yt.template`, `yt.title-template`, `yt.title`, `yt.title-suffix`, `yt.description: verbatim`, `yt.var.<name>` to the directive parser in `src/livestream_scheduler/calendar/mapping.py`.

**Checkpoint**: The templating unit tests pass.

---

## Phase 3: User Story 1 - Use a reusable description template for every livestream (Priority: P1) 🎯 MVP

**Goal**: The default templates render each occurrence's description, and titles too (title templating was added by 003 FR-004). With no template configured, behavior is exactly 001's.

**Independent Test**: A default description template referencing `title`, `date_long` and `notes`, with two calendar events → each published description contains the shared boilerplate with that event's values. Removing the template restores the calendar notes.

### Tests for User Story 1 ⚠️

- [ ] T013 [P] [US1] Write `tests/integration/templating/test_us1_acceptance.py`:
  - US1-1: placeholders replaced per event
  - US1-2: no template → the description equals the calendar notes and the title equals SUMMARY (002 FR-014)
  - US1-3: a `.md.j2` with headings, lists and links publishes clean plain text, with no `**` or `#`
- [ ] T014 [P] [US1] Write `tests/unit/templating/test_render_determinism.py`: rendering every fixture twice gives identical output. 20 consecutive syncs with nothing changed → 0 updates (002 FR-016, SC-005).

### Implementation for User Story 1

- [ ] T015 [US1] Implement `src/livestream_scheduler/templating/render.py`:
  - `render(occurrence_ctx, title_templates: list[str] | None, description_template: str | None) -> Rendered(title, description, warnings, templates_used)`
  - `title_template` may be a **list** of fallbacks: use the first candidate whose limited title is ≤ 100 chars, with a warning per step down (004 S3)
  - picks the `.txt.j2` vs `.md.j2` pipeline by extension
  - applies the limits
  - `yt.title` (verbatim) and `yt.description: verbatim` bypass rendering
- [ ] T016 [US1] Integrate rendering into `src/livestream_scheduler/sync/run.py`: mapping produces base values, then `build_context`, then `render`. `occurrence.title`/`description` store the **rendered** text, and `desired_hash` covers rendered title, description, privacy and times (T5). No template configured → the 001 values unchanged.
- [ ] T017 [US1] Add `db/schema/0002_templates.sql`, adding `occurrence.title_template TEXT NULL`, `occurrence.description_template TEXT NULL`, `occurrence.render_warnings TEXT NULL` (JSON list) and `occurrence.values_json TEXT NULL`. Register it in `migrate.py`.

**Checkpoint**: US1 tests pass. 001's acceptance tests still pass unchanged.

---

## Phase 4: User Story 2 - Choose different templates for different kinds of streams (Priority: P2)

**Goal**: Named templates can be chosen per event or series.

**Independent Test**: Two named templates, with one series marked `yt.template: deep-dive` → that series uses it and the others use the default. A missing template name → `failed` and a notification.

### Tests for User Story 2 ⚠️

- [ ] T018 [P] [US2] Write `tests/integration/templating/test_us2_acceptance.py`:
  - US2-1: the series directive applies to every instance; an instance override wins
  - US2-2: an unknown template → occurrence `failed` with the reason naming the template, nothing published, and one notification

### Implementation for User Story 2

- [ ] T019 [US2] Implement template selection in `src/livestream_scheduler/templating/render.py` (T6 order): the `yt.template`/`yt.title-template` directive, then (003/004 hook: the type's templates), then `templates.default_*`, then none
- [ ] T020 [US2] Implement render-failure handling in `src/livestream_scheduler/sync/run.py` (002 FR-008):
  - a template error → the occurrence `failed` with `state_reason = "Template <name>: <file:line message>"`
  - an already-`scheduled` occurrence keeps its last published text, and nothing is pushed
  - notification key `template:<name>`

---

## Phase 5: User Story 3 - Preview and update descriptions safely (Priority: P3)

**Goal**: Preview without publishing, validate templates, and propagate template edits to every managed upcoming livestream.

**Independent Test**: `preview` shows the final text with no API writes. Editing a snippet → next sync updates all affected occurrences, and a second sync updates 0. A broadcast edited by hand is not overwritten.

### Tests for User Story 3 ⚠️

- [ ] T021 [P] [US3] Write `tests/integration/templating/test_us3_acceptance.py`:
  - US3-1: `preview` makes 0 API calls and prints warnings
  - US3-2: a snippet edit → N updates, then 0
  - US3-3: an `owner_modified` occurrence is not overwritten

### Implementation for User Story 3

- [ ] T022 [US3] Add the CLI commands `preview [<id> | --date YYYY-MM-DD] [--next N=3] [--offline]` and `templates check` to `src/livestream_scheduler/cli.py`:
  - preview: title and description with char and byte counts, the templates used, the values with their source, and warnings
  - templates check: renders every configured and bundled template against fixture contexts; `file:line: message`; exit 2 on error
- [ ] T023 [US3] Make `config check` (001) also run `templates check`, in `src/livestream_scheduler/cli.py`

---

## Phase 6: Polish

- [ ] T024 [P] Add `examples/templates/` with an example `.md.j2` description and an example `snippets/` include. Document the template context in `README.md` (link to 003 contracts/template-values.md).
- [ ] T025 (`tests/`) Run `uv run pytest`, `uv run ruff check` and `uv run mypy src`, then verify that 001's quickstart scenarios 2–3 still give 0 extra updates.

---

## Dependencies & Execution Order

- 001 Phases 1–4 → Setup T001–T002 → Foundational T003–T012 → US1 T013–T017 → US2 T018–T020 → US3 T021–T023 → Polish.
- 003 extends `context.py` (`service.*`) and `render.py` selection (type templates). Keep those extension points as clear hooks.

## Parallel Opportunities

- T003–T006 (tests) together. T008–T010 together. T013/T014 together.

## Implementation Strategy

US1 alone is already valuable (shared boilerplate). Ship US1 and US2, then continue to [003 tasks](../003-lectionary-service-metadata/tasks.md), which supply the Minnehaha defaults. Preview (US3) can be done in parallel with 003.
