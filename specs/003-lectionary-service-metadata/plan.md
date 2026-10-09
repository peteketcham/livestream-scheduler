# Implementation Plan: Lectionary-Based Titles and Descriptions (includes 002 templating)

**Branch**: `003-lectionary-service-metadata` | **Date**: 2026-10-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-lectionary-service-metadata/spec.md`. Also covers [002-description-templates](../002-description-templates/spec.md), which has no separate plan (research preamble).

**Builds on**: [001 plan](../001-youtube-livestream-scheduler/plan.md). All 001 technical choices stand.

## Summary

Every scheduled Minnehaha UMC livestream gets a title and description rendered from templates. Sunday-morning events, and any event marked as a service, are church services. For those, the template context includes:
- the liturgical day name, lectionary year and season, **computed locally** from the lectionary calendar rules. This was verified against the site's 2019–2026 export.
- any owner-listed special day, shown in parentheses (e.g. "(All Saints Sunday)").
- readings, color and series titles **read from the Discipleship Ministries planning pages**, cached and validated.

The bundled templates reproduce the church's existing format byte-for-byte: `October 4th, 2026 - Nineteenth Sunday after Pentecost`, plus the welcome line, bulletin, links and licensing footer. Rendered text feeds 001's existing hash-based update path. Template, snippet or lectionary changes therefore propagate in one run, unchanged inputs cause no updates, and manual edits on YouTube are still respected.

## Technical Context

**Language/Version**: Python 3.12 (as 001)

**Primary Dependencies**: the 001 dependencies plus Jinja2 3.1 (sandboxed), markdown-it-py 3.x, and beautifulsoup4 4.12 (stdlib `html.parser`). See research T1, T2 and L9.

**Storage**: SQLite (001), extended by migrations `0002_templates` (002) and `0003_lectionary_service_types` (003) ([data-model.md](data-model.md)). Template files live in `templates.dir`, with bundled defaults in the package.

**Testing**: pytest (as 001), plus:
- golden-output tests against the two reference livestreams
- an oracle test against the site's 412-entry export
- parser fixtures (saved and mutated HTML)
- sandbox-escape tests
- determinism and property tests

**Target Platform**: as 001 (owner's home Ubuntu Server 24.04 LTS, systemd timer, uv runner). macOS for development only.

**Project Type**: CLI application (single project, as 001)

**Performance Goals**: Rendering takes < 50 ms per occurrence. A no-change `sync` makes ≤ 2 lectionary HTTP requests (conditional), and 0 when the cache is fresh.

**Constraints**:
- Output is deterministic (no clock or locale dependence).
- Templates cannot read files outside their folder, the network, the environment or secrets.
- At most one fetch per page per 24 h. The `User-Agent` carries no owner email.
- The site's prose is not republished by default.
- A title is ≤ 100 characters, a description ≤ 5000 bytes, and `<` `>` are stripped.

**Scale/Scope**: About 4–6 service occurrences per horizon and about 6 site requests per day.

Every Technical Context item is resolved. The spec has no NEEDS CLARIFICATION. The clarification session ended after 2 of 3 questions. The unanswered one (whether readings go in the default description) keeps the spec default: readings are available to templates but **not** in the bundled description, matching the church's current format.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is still the unfilled template, so it sets no ratified gates. As in 001, this plan applies a stated baseline. The owner's instruction to use **Conventional Commits** is added to it.

| Baseline principle | How this plan satisfies it | Pre | Post |
|---|---|---|---|
| Test-first, core logic testable offline | Pure `liturgy.calendar` and renderer. Saved HTML/ICS fixtures. Golden and oracle tests. No network in unit or integration tests. | ✅ | ✅ |
| Simplicity / YAGNI | No new process, service or store. Three small libraries. Defaults are plain files. Special days are a config list, not a rules engine. | ✅ | ✅ |
| Safety of a public channel | StrictUndefined. Failed renders never publish. Last-good lectionary data is never overwritten. Site data is validated (date, references, color). Existing 001 manual-edit and mass-removal guards remain. | ✅ | ✅ |
| Security | Jinja sandbox with an allowlisted context. Loader confined to the templates folder. No secrets in context or `values_json`. No email in the User-Agent. | ✅ | ✅ |
| Observability | `preview` shows the source of every value. `lectionary show`. Run items `lectionary_pending` / `lectionary_invalid`. Deduplicated notifications. | ✅ | ✅ |
| Respect for third parties | robots.txt honored. Conditional requests and a 24 h refresh. Prose opt-in with mandatory credit (research L5, L6). | ✅ | ✅ |
| **Development workflow: Conventional Commits** | Every commit is `type(scope): summary` (feat, fix, docs, test, refactor, chore, build, ci). Scopes come from the module names: `liturgy`, `lectionary`, `templating`, `service`, `cli`, `sync`, `db`, `specs`. Example: `feat(liturgy): compute Sundays after Pentecost`. Task generation (`/speckit-tasks`) should suggest one commit message per task. | ✅ | ✅ |

**Post-design re-check**: the design adds modules inside the existing package, one migration, and no new runtime services. There are no violations. A spec amendment was made from research, recorded in spec.md "Amendments from planning research": day names are computed, not scraped. It *reduces* dependence on the external site and removes title churn, so it simplifies rather than adds complexity.

## Project Structure

### Documentation (this feature)

```text
specs/003-lectionary-service-metadata/
├── plan.md                 # This file
├── research.md             # T1–T6 (templating/002), L1–L10 (lectionary/003)
├── data-model.md           # migration 0002: occurrence columns, lectionary_day, lectionary_source
├── quickstart.md           # validation scenarios for 002 + 003
├── reference/
│   └── sunday-examples.md  # verbatim reference livestreams (golden oracle)
├── contracts/
│   ├── template-values.md      # everything a template can see + filters
│   ├── default-templates.md    # bundled Minnehaha templates and exact expected renders
│   ├── liturgical-calendar.md  # naming rules, year/season, special-day rules, worked examples
│   ├── config-additions.md     # templates / service / lectionary config + new directives
│   └── cli-additions.md        # preview, templates check, lectionary show/refresh
├── checklists/requirements.md
└── tasks.md                # Phase 2 (/speckit-tasks)
```

### Source Code (additions to 001's layout)

```text
src/livestream_scheduler/
├── templating/
│   ├── env.py              # SandboxedEnvironment, StrictUndefined, loader chain (dir → bundled)
│   ├── filters.py          # ordinal, strftime (English), date_long, join_readings, md
│   ├── plaintext.py        # markdown-it-py → plain-text renderer (for .md.j2)
│   ├── limits.py           # title/description limits, forbidden chars, warnings
│   └── render.py           # select templates (T6), build context, render, validate
├── liturgy/
│   ├── calendar.py         # computus, anchors, names, year, season, default color
│   └── special_days.py     # owner rule list → special_names
├── lectionary/
│   ├── fetch.py            # polite HTTP: robots, conditional GET, rate limit, User-Agent
│   ├── listing.py          # listing page → {date: planning_url}, export URL discovery
│   ├── planning_page.py    # parse + validate references, color, week/series titles
│   ├── export.py           # site ICS cross-check (L4)
│   └── store.py            # lectionary_day / lectionary_source persistence, last-good rule
├── service.py              # service detection (L7), value merge + overrides (L8) → service context
├── defaults/templates/
│   ├── service-title.txt.j2
│   ├── service-description.txt.j2
│   └── snippets/minnehaha-footer.txt.j2
├── db/schema/0003_lectionary_service_types.sql   # (002 adds 0002_templates.sql)
└── (001 modules touched)
    ├── calendar/mapping.py # now produces base event values; rendering moved to templating/
    ├── sync/run.py         # refresh lectionary → render → plan (unchanged planner)
    └── cli.py              # preview, templates check, lectionary show/refresh

tests/
├── fixtures/lectionary/    # umc-2019-2026.ics, listing-2026-10-08.html, planning-2026-10-18.html, mutated/*
├── fixtures/reference/     # golden titles/descriptions from reference/sunday-examples.md
├── unit/liturgy/  unit/templating/  unit/lectionary/  unit/test_service.py
└── integration/test_golden_sundays.py, test_template_propagation.py, test_lectionary_outage.py
```

**Structure Decision**: The single 001 package gains three cohesive subpackages: `templating` (feature 002), and `liturgy` plus `lectionary` (feature 003), joined by `service.py`. The sync planner is untouched. Templating only changes what the desired title and description are, so 001's idempotence, manual-edit and quota guarantees carry over without new code paths.

## Delivery order (for /speckit-tasks)

1. **001 MVP** (scheduler with calendar SUMMARY/notes).
2. **002 templating** (T1–T6; default templates off).
3. **003 liturgy** (pure, oracle-tested). Enable the bundled service templates, which already satisfy US1 without any site fetching.
4. **003 lectionary fetch** (readings, color, series), plus preview/show.

Each step can ship on its own, and step 3 already delivers the user's core request.

## Complexity Tracking

There are no constitution violations, so this section is empty.
