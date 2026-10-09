# Quickstart & Validation: Templates + Lectionary (002 + 003)

Prerequisites: 001's [quickstart](../001-youtube-livestream-scheduler/quickstart.md) setup is done (config, `connect`). The stream calendar has a weekly **Sunday 9:30 AM America/Chicago** event of about 75 min. Contracts: [template-values](contracts/template-values.md), [default-templates](contracts/default-templates.md), [liturgical-calendar](contracts/liturgical-calendar.md), [config-additions](contracts/config-additions.md), [cli-additions](contracts/cli-additions.md).

## Automated validation

```bash
uv run pytest tests/unit/liturgy            # computed names; worked examples + 2019–2026 export oracle
uv run pytest tests/unit/templating         # sandbox, StrictUndefined, ordinal, md→text, limits, determinism
uv run pytest tests/unit/lectionary         # planning-page parser on saved + mutated fixtures
uv run pytest tests/integration -k "golden or lectionary or template"
```

Expected:
- **Golden** (SC-001a): the Sept 27 and Oct 4, 2026 renders equal `reference/sunday-examples.md` byte-for-byte, except "Nineteenth" capitalized.
- **Oracle**: 0 new divergences.
- **Sandbox**: escape attempts fail validation.

## Manual scenarios (no YouTube writes needed until step 6)

| # | Steps | Expected | Proves |
|---|---|---|---|
| 1 | `livestream-scheduler templates check` | `ok` (bundled defaults) | 002 FR-011 |
| 2 | `livestream-scheduler lectionary show 2026-10-18` | Twenty-First Sunday after Pentecost, A. Readings Exodus 33:12-23; Psalm 99; 1 Thessalonians 1:1-10; Matthew 22:15-22. Green. Series "Always Give Thanks" / "Chosen". Site name matches. | 003 FR-002, L1/L3 |
| 3 | `livestream-scheduler preview --date 2026-10-18` | Title `October 18th, 2026 - Twenty-First Sunday after Pentecost`. Description as in default-templates.md. Sources listed. | 003 US1-1, US1-6 |
| 4 | `preview --date 2026-11-01` and `--date 2026-11-22` | Titles with `(All Saints Sunday)` / `(Reign of Christ / Christ the King Sunday)` | Clarification 2 |
| 5 | Add a Sunday 2:00 PM event, then `occurrences`. Then add `yt.service: yes` to its notes. | First not a service. After the directive, a service. | Clarification 1 |
| 6 | `sync` on the test channel, then open YouTube Studio | Titles and descriptions as previewed | 003 SC-001 |
| 7 | Edit `snippets/minnehaha-footer.txt.j2` (change a license number), then `sync` | Every upcoming managed service is updated. Run shows N updated. A second `sync` shows 0 updated. | 002 SC-001, SC-005 |
| 8 | Introduce `{{ servce.label }}` into a template, then `sync` | Exit 1. Affected occurrences `failed` with `file:line`. Published streams unchanged. Email sent. | 002 FR-008, SC-003 |
| 9 | Set `lectionary.listing_url` to an unreachable host, then `sync` | Titles unchanged (computed). No published text reverted. One `lectionary:fetch` email. | 003 FR-008, SC-005 |
| 10 | Add `yt.readings: Psalm 23` and `yt.title: Guest Preacher Sunday` to one instance, then `preview` | Only that instance is overridden. Sources show `override`. | 003 US3 |
