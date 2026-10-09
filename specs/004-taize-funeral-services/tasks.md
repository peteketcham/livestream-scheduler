---
description: "Task list for 004 Taizé Services and Funerals"
---

# Tasks: Taizé Services and Funerals (004)

**Input**: `specs/004-taize-funeral-services/`: plan.md, spec.md (5 clarifications), research.md (S1–S10), data-model.md, contracts/ (service-types, templates, cli-additions), quickstart.md

**Prerequisites**:
- [001 tasks](../001-youtube-livestream-scheduler/tasks.md) complete. **The hand-made livestream guard (004 S6) is built there as 001:T042/T047**, together with the `exists_external` state and the `external_*` columns.
- [002 tasks](../002-description-templates/tasks.md) Phases 1–4, including title fallback lists (002:T015).
- [003 tasks](../003-lectionary-service-metadata/tasks.md) Phases 1–3, including the registry core and classification (003:T011–T012) and the three-part footer (003:T018).

**Migration**: `0004_service_type_details.sql`.

**Tests**: INCLUDED. **Commits**: Conventional Commits with scopes `service-types`, `templates`, `notify`, `cli`.

## Format: `[ID] [P?] [Story] Description`

[Story] = US1/US2/US3 from `specs/004-taize-funeral-services/spec.md`.

---

## Phase 1: Setup

- [ ] T001 Create `tests/integration/service_types/` and `tests/fixtures/ics/`:
  - `taize-monthly.ics`: RRULE monthly on the second Friday 19:00 America/Chicago, SUMMARY "Taizé"; plus one single event "Taize Prayer" on 2026-11-13
  - `funeral.ics`: "Funeral for Jane Doe" on 2026-10-23 11:00; "Funeral" with no name; "Celebration of Life – José O'Brien-Smith" with `yt.years: 1941–2026`; a 70-character name with `yt.wording: Celebration of Life`

---

## Phase 2: Foundational (Blocking Prerequisites)

- [ ] T002 Write `db/schema/0004_service_type_details.sql`: add `occurrence.type_values_json TEXT NULL` and `occurrence.announced_start_utc TEXT NULL` (data-model.md). Register it in `migrate.py`.
- [ ] T003 [P] Write `tests/unit/service_types/test_keywords.py` (S1):
  - `Taizé`, `Taize`, `TAIZÉ`, `Taizé Prayer` → `taize (keyword)`
  - `Memorials Committee` → **not** funeral (whole word)
  - `Celebration of Life – X` → funeral
  - `yt.type: taize` beats the Sunday rule; a keyword beats the Sunday rule (a Taizé on Sunday 09:30 → taize)
  - unknown `yt.type: wedding` → `failed` with `Unknown service type "wedding" (known: worship, taize, funeral)`
- [ ] T004 Extend `src/livestream_scheduler/service_types/registry.py` with the full option set in contracts/service-types.md:
  - `match.keywords`, `visibility_source` (`any`|`instance_only`), `requires`, `announce`, `details`
  - bundled default entries `taize` and `funeral`, in the order worship, taize, funeral, with the exact values in contracts/service-types.md
  - validation: `other` is reserved, ids are unique, `requires` paths exist, at most one `lectionary: true` per day (warning)
- [ ] T005 Extend `src/livestream_scheduler/service_types/classify.py` with keyword matching: NFKD, strip combining marks, casefold, whole word or phrase via `\b`-bounded regex over the normalized title, first match in registry order (S1)
- [ ] T006 Expose `service_type` and `<type>.*` details in `src/livestream_scheduler/templating/context.py` (003 contracts/template-values.md additions)

**Checkpoint**: Keyword classification passes. Sunday worship golden tests (003:T015) still pass.

---

## Phase 3: User Story 1 - Taizé services recognized and titled consistently (Priority: P1) 🎯 MVP

**Goal**: Every calendar Taizé gets `<date> - Taizé` and the Taizé description. The hand-made Oct 9 Taizé is not duplicated.

**Independent Test**: `taize-monthly.ics` + FakeYouTube pre-seeded with the hand-made Oct 9 Taizé:
- Oct 9 → `exists_external`, with 0 writes to that id;
- Nov 13 → created with title `November 13th, 2026 - Taizé` and line 1 `Welcome to Minnehaha United Methodist Church on November 13th, 2026 for Taizé prayer!`;
- 0 Sunday wording.

### Tests for User Story 1 ⚠️

- [ ] T007 [P] [US1] Write `tests/integration/service_types/test_taize_golden.py` with the Taizé "Expected renders" rows in contracts/templates.md (Oct 9 and Nov 13 "Taize Prayer"). Assert there is no `Sunday`, no `Pentecost`, and the full footer is byte-identical to the worship footer.
- [ ] T008 [P] [US1] Write `tests/integration/service_types/test_taize_acceptance.py`:
  - US1-1, US1-2, US1-3 (each instance in the horizon dated correctly)
  - US1-4: the pre-seeded hand-made broadcast at 2026-10-10T00:00Z → `exists_external`, one "Already on the channel" email (001:T053), no insert

### Implementation for User Story 1

- [ ] T009 [P] [US1] Add `src/livestream_scheduler/defaults/templates/taize-title.txt.j2` (`{{ date_long }} - Taizé`) and `taize-description.txt.j2` (`Welcome to {{ church_name }} on {{ date_long }} for Taizé prayer!`, a blank line, `{% include "snippets/minnehaha-footer.txt.j2" %}`), exactly as in contracts/templates.md
- [ ] T010 [US1] Apply each type's `default_duration_minutes` (taize: 65) in `src/livestream_scheduler/calendar/mapping.py` / `sync/run.py` when the calendar event has no DTEND/DURATION. This replaces 001's +1 h default for typed occurrences.

**Checkpoint**: Taizé is complete, and safe at cut-over.

---

## Phase 4: User Story 2 - Short-notice funerals with a ready-made template (Priority: P2)

**Goal**: Calendar funerals → an unlisted livestream with a respectful title, no Sunday bulletin, and the watch link emailed to the owner on create, change and cancel.

**Independent Test**: `funeral.ics` →
- Jane Doe: title `October 23rd, 2026 - Funeral for Jane Doe`, **unlisted**, line 1 `Welcome to Minnehaha United Methodist Church on October 23rd, 2026 for the funeral of Jane Doe.`, one email with `https://youtu.be/<id>`;
- the no-name "Funeral" → `failed` and not published;
- `defaults.visibility: public` → funerals still unlisted.

### Tests for User Story 2 ⚠️

- [ ] T011 [P] [US2] Write `tests/unit/service_types/test_funeral_details.py` (S2):
  - name from the title `Funeral for Jane Doe`, `Funeral: Jane Doe`, `Funeral – Jane Doe`, `Celebration of Life – José O'Brien-Smith`
  - `yt.name` wins over the title
  - the name is kept exactly (accents, apostrophes, hyphens); only `<` `>` are removed, with a warning
  - `wording` defaults to `Funeral`
  - a missing name → `failed` with the reason `Funeral needs a name: add "yt.name: …" to the event notes or title it "Funeral for <name>"`
- [ ] T012 [P] [US2] Write `tests/unit/service_types/test_visibility.py` (S4): the matrix of {`defaults.visibility` public/unlisted/private} × {series `yt.visibility` none/public} × {instance `yt.visibility` none/public/private}. A funeral is public **only** when the instance says public. `values_json.visibility_reason` is `type_default` or `instance_directive`.
- [ ] T013 [P] [US2] Write `tests/integration/service_types/test_funeral_golden.py` with every funeral row of "Expected renders" in contracts/templates.md:
  - the Jane Doe default
  - Celebration of Life with years and obituary
  - the 70-char name falling back to `funeral-title-short` with a warning and the name intact
  - no `Peace and good health` and no bulletin line in any funeral description
- [ ] T014 [P] [US2] Write `tests/integration/service_types/test_funeral_lifecycle.py` (S5, FR-009a):
  - create → exactly one "scheduled" email containing the youtu.be URL
  - a wording change only → no email
  - a time move → one "changed" email; delete from the calendar → one "removed" email
  - 10 repeated runs → no more emails
  - SMTP down at create → retried on the next run, and scheduling is not blocked
  - every email goes only to `notify.email_to`

### Implementation for User Story 2

- [ ] T015 [P] [US2] Implement `src/livestream_scheduler/service_types/details.py`: read `details` directives (`yt.name`, `yt.wording`, `yt.years`, `yt.obituary` (kind url), `yt.memorials`), extract the name from the title with the regex `^(?:funeral|memorial(?: service)?|celebration of life)\s*(?:for|of|:|–|-)\s*(?P<name>.+)$` (normalized-insensitive match, original-case capture), and enforce `requires`. Store the values with a per-value source in `occurrence.type_values_json`.
- [ ] T016 [P] [US2] Implement `src/livestream_scheduler/service_types/visibility.py` (S4): `effective_visibility(type, instance_directives, series_directives, defaults) -> (visibility, reason)`, honoring `visibility_source: instance_only`. Log an info line when a funeral becomes public by an event setting.
- [ ] T017 [P] [US2] Add the bundled funeral templates in `src/livestream_scheduler/defaults/templates/`: `funeral-title.txt.j2`, `funeral-title-short.txt.j2`, `funeral-title-shortest.txt.j2` and `funeral-description.txt.j2`, exactly as in contracts/templates.md (the links and licensing snippets only, no bulletin)
- [ ] T018 [US2] Wire details, `requires` and effective visibility into `src/livestream_scheduler/sync/run.py` before rendering. A missing required value → `failed` + 001 notification `occurrence:<id>:failed`.
- [ ] T019 [US2] Implement the announce emails in `src/livestream_scheduler/notify.py` and `sync/run.py` (S5):
  - sent after a committed create, update or delete for types with `announce: true`
  - subjects and bodies per contracts/cli-additions.md
  - dedup keys `announce:<occ>:created:<start_utc>`, `announce:<occ>:changed:<start_utc>`, `announce:<occ>:cancelled`, one-shot and resolved immediately after a successful send
  - "changed" only when the start differs from `announced_start_utc`; update `announced_start_utc` after a send
  - a run_item action `announce`
- [ ] T020 [US2] Add the CLI command `link (<occurrence-id> | --date YYYY-MM-DD) [--type <id>]` and the `occurrences --type <id>` filter with a `type` column (type and reason) to `src/livestream_scheduler/cli.py` (contracts/cli-additions.md; exit 3 with a reason when no livestream exists yet; `--json` shape)

**Checkpoint**: Funerals are complete. All quickstart scenarios 5–11 pass against FakeYouTube.

---

## Phase 5: User Story 3 - Owner can adjust each service type (Priority: P3)

**Goal**: Types are changed or added through config and templates alone.

**Independent Test**: Add a `wedding` type (keyword "wedding", unlisted, its own templates) in a test config, plus an edited Taizé template → preview reflects both. A sync updates upcoming Taizés exactly once.

### Tests for User Story 3 ⚠️

- [ ] T021 [P] [US3] Write `tests/integration/service_types/test_custom_type.py`: US3-1 (a Taizé template edit → N updates, then 0) and US3-2 (a new `wedding` type is matched and rendered with its templates, with no code changes)

### Implementation for User Story 3

- [ ] T022 [US3] Make `config check` / `templates check` in `src/livestream_scheduler/cli.py` list the configured types (`worship, taize, funeral, other`), each with its match rules, templates and visibility, and validate owner-added types (contracts/service-types.md "Validation")
- [ ] T023 [P] [US3] Add `examples/service-types/wedding.yaml` and `examples/templates/wedding-title.txt.j2` / `wedding-description.txt.j2` as a copyable example of adding a type (SC-006)

---

## Phase 6: Polish

- [ ] T024 [P] Document in `README.md`:
  - service types and the `yt.type` directive
  - how to enter funerals (title "Funeral for <name>", optional `yt.wording`/`yt.years`/`yt.obituary`/`yt.memorials`, unlisted by default, the link arrives by email)
  - Google ICS lag advice
  - `systemctl start livestream-scheduler.service` for an immediate run
- [ ] T025 Run 004 quickstart.md manual scenarios 1–11 on the test channel. `uv run pytest`, `uv run ruff check` and `uv run mypy src` all pass.

---

## Dependencies & Execution Order

- 001 (all) + 002 (1–4) + 003 (1–3) → T001 → T002–T006 → **US1 T007–T010** → **US2 T011–T020** → US3 T021–T023 → Polish.
- US2 does not depend on US1 (different types). Both depend on Phase 2. US3 depends on Phase 2 only.

## Parallel Opportunities

- T003 with T002. US1: T007–T009 together. US2: tests T011–T014 together, then T015–T017 together. US3: T021 and T023.

## Implementation Strategy

1. **US1 (Taizé)** first. It is the next most frequent stream after Sundays, and it's currently hand-made with copied Sunday text.
2. **US2 (funerals)** next. It is time-sensitive and privacy-sensitive, with the full test matrix before any live funeral.
3. US3 (owner-defined types) whenever the church needs weddings or concerts.
