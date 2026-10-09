# Implementation Plan: Taizé Services and Funerals

**Branch**: `004-taize-funeral-services` | **Date**: 2026-10-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-taize-funeral-services/spec.md`

**Builds on**:
- [001 plan](../001-youtube-livestream-scheduler/plan.md): scheduler, systemd + uv deployment.
- [003 plan](../003-lectionary-service-metadata/plan.md): templating (002), liturgy, lectionary.

## Summary

The yes/no "church service" flag from 003 is generalized into a configurable **service-type registry**: `worship`, `taize`, `funeral` and the implicit `other`. Each occurrence is classified by directive, then title keyword, then day/time rule. Each type brings its own:
- title templates, with a fallback chain;
- description template;
- visibility, including a funeral-only lock that keeps funerals unlisted unless the event itself says public;
- default duration;
- whether lectionary values are used.

Taizé gets consistent titles (`October 9th, 2026 - Taizé`) and its own welcome line. Funerals:
- come from the calendar;
- need a name, taken from `yt.name` or from a title like "Funeral for Jane Doe";
- render as unlisted;
- email the watch link to the owner on create, move and cancel.

A new planner step checks the channel's upcoming livestreams before creating anything. A hand-made livestream within ±15 min blocks the create, is reported once, and is never modified. This protects the cut-over, including the existing hand-made Oct 9 Taizé.

## Technical Context

**Language/Version**: Python 3.12 (as 001)

**Packaging/Runner**: uv (as 001 R16)

**Primary Dependencies**: none new. It uses Jinja2 (003 T1), the 001 notifier and `YouTubePort.list_upcoming`, and stdlib `unicodedata` for accent-insensitive matching.

**Storage**: SQLite. Migration `0004_service_type_details.sql` ([data-model.md](data-model.md)). `service_type` and `type_reason` arrive in 003's `0003`, and the `external_*` columns in 001's `0001`. Types are YAML config.

**Testing**: pytest via `uv run`. Unit tests (classification, name extraction, visibility matrix, title fallbacks), golden renders ([contracts/templates.md](contracts/templates.md)), and integration tests with `FakeYouTube` (external-conflict lifecycle, email dedup).

**Target Platform**: as 001 (owner's home Ubuntu Server 24.04 LTS, systemd timer, uv runner). macOS for development.

**Project Type**: CLI application (single project)

**Performance Goals**: Classification and rendering take < 50 ms per occurrence. The external-conflict check costs ≤ 1 quota unit per run, and only when creates are planned or `exists_external` rows exist.

**Constraints**:
- Funerals are never public by default.
- Hand-made livestreams are never modified.
- Funeral names are never truncated or reformatted.
- Emails go only to the owner's address.
- Sunday worship output stays byte-identical to 003 (SC-001a).

**Scale/Scope**: About 4 worship, 1 Taizé and 0–2 funerals per 4-week horizon.

No NEEDS CLARIFICATION remain. The spec had 5 clarifications on 2026-10-08: calendar-only funerals, calendar-only Taizé, no adoption of hand-made livestreams, names exactly as entered with unlisted by default, and the link emailed to the owner.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is still the unfilled template, so it sets no ratified gates. This plan applies the baseline from 001 and 003, including the owner's workflow directions: Conventional Commits, systemd timers over cron, and uv.

| Baseline principle | How this plan satisfies it | Pre | Post |
|---|---|---|---|
| Test-first, offline | Pure `classify()` and renderer. FakeYouTube covers hand-made livestreams. Golden outputs for every bundled template. | ✅ | ✅ |
| Simplicity / YAGNI | One registry instead of per-type code. Reuses templating, notifier and listing. No new dependency or process. 003's parenthetical rule is folded into the generic title-fallback mechanism. | ✅ | ✅ |
| Safety of a public channel | The hand-made-livestream guard (S6) with the ownership rule unchanged. Funeral visibility lock (S4). Required-value check blocks publishing without a name. | ✅ | ✅ |
| Privacy | Funerals are unlisted by default and immune to global or series visibility. Emails go to the owner only. Names appear only as the volunteer entered them. | ✅ | ✅ |
| Observability | `type_reason` in previews and listings. `link` command. Run items `external_conflict`/`announce`. Deduplicated emails. | ✅ | ✅ |
| Workflow | Conventional Commits with scopes `service-types`, `templates`, `sync`, `notify`, `cli`, `db`. uv for running and testing. systemd for scheduling (unchanged). | ✅ | ✅ |

**Post-design re-check**: no violations. There are two cross-feature changes, both recorded in the affected docs:
1. 003's service-detection config keys move into `service_types[worship]`. 003 uses the `service_type` column from the start, so there is never an `is_service` column.
2. 001's planner gains the external-conflict step and the `exists_external` state.

Both are additive, and neither changes observable 001 or 003 behavior apart from preventing duplicates.

## Project Structure

### Documentation (this feature)

```text
specs/004-taize-funeral-services/
├── plan.md              # This file
├── research.md          # S1–S10
├── data-model.md        # migration 0003: service_type, external_*, announced_start_utc; state additions
├── quickstart.md        # validation scenarios
├── contracts/
│   ├── service-types.md # registry config, classification precedence, options
│   ├── templates.md     # footer parts, Taizé + funeral templates, exact expected renders
│   └── cli-additions.md # link, occurrences --type, emails
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (additions/changes to the 001 + 003 layout)

```text
src/livestream_scheduler/
├── service_types/
│   ├── registry.py          # load/validate service_types config, bundled defaults
│   ├── classify.py          # precedence: directive > keyword (NFKD/casefold/whole-word) > rule > other
│   ├── details.py           # per-type details from directives; funeral name-from-title; `requires`
│   └── visibility.py        # visibility_source rules (S4)
├── templating/render.py     # (changed) title_template lists → first fitting candidate (S3)
├── service.py               # (changed) lectionary context only when type.lectionary
├── sync/
│   ├── external.py          # S6: list_upcoming once, ±15 min match, exists_external lifecycle
│   └── run.py               # (changed) classify → render → external check → plan → execute → announce
├── notify.py                # (changed) one-shot announce emails + external-conflict notice
├── cli.py                   # (changed) `link`, `occurrences --type`, preview shows type/reason
├── defaults/templates/
│   ├── snippets/{bulletin,links,licensing,minnehaha-footer}.txt.j2
│   ├── taize-{title,description}.txt.j2
│   └── funeral-{title,title-short,title-shortest,description}.txt.j2
└── db/schema/0004_service_type_details.sql

tests/
├── unit/service_types/      # classify, details, visibility matrix
├── unit/templating/test_title_fallbacks.py, test_footer_parts.py
└── integration/test_taize.py, test_funeral_lifecycle.py, test_external_conflict.py
```

**Structure Decision**: A new `service_types` subpackage holds everything type-specific. The planner and executor stay type-agnostic. Types only change the rendered desired state and the visibility, plus two hooks: the external check before creates, and the announce step after commits.

## Delivery order (for /speckit-tasks)

This extends the order in 003's plan:
1. **001 MVP**, now **including the external-conflict guard (S6)**. It must ship before the first live run, so the hand-made Oct 9 Taizé isn't duplicated.
2. 002 templating, with title-fallback lists (S3).
3. 003 liturgy plus the service-type registry with `worship`.
4. **004 Taizé** type and templates, plus the footer split.
5. **004 Funeral** type: details, visibility lock, announce emails, `link`.
6. 003 lectionary fetch (readings, color, series): optional enrichment, last.

## Complexity Tracking

There are no constitution violations, so this section is empty.
