# Quickstart & Validation: Taizé Services and Funerals

Prerequisites: the 001 server deployment and the 003 setup are done ([001 quickstart](../001-youtube-livestream-scheduler/quickstart.md), [003 quickstart](../003-lectionary-service-metadata/quickstart.md)). Contracts: [service-types](contracts/service-types.md), [templates](contracts/templates.md), [cli-additions](contracts/cli-additions.md).

## Automated validation

```bash
uv run pytest tests/unit/service_types      # classification precedence, keyword normalization, funeral name extraction, visibility matrix
uv run pytest tests/unit/templating -k "fallback or footer"
uv run pytest tests/integration -k "taize or funeral or external"
```

Expected:
- **Golden renders**: the outputs in contracts/templates.md match exactly, and the Sunday worship golden from 003 is still byte-identical after the footer split.
- **External-conflict test**: the fake channel holds a hand-made Taizé at 2026-10-10T00:00Z, giving `exists_external` and 0 inserts. After it is removed from the fake, the next run creates one.
- **Funeral email test**: exactly one email per create, change or cancel, across 10 repeated runs.

## Manual scenarios

| # | Steps | Expected | Proves |
|---|---|---|---|
| 1 | `lss config check` | Lists types `worship, taize, funeral, other`. `ok`. | FR-001, FR-012 |
| 2 | Calendar: recurring "Taizé", second Friday 7:00 PM. `lss preview --date 2026-11-13` | `November 13th, 2026 - Taizé`, Taizé welcome line, full footer, type `taize (keyword)` | US1-1, US1-3 |
| 3 | `lss sync --dry-run` while the hand-made Oct 9 Taizé exists | The Oct 9 occurrence is `exists_external` with that video's link. No create is planned for it. Later Taizés are planned. | US1-4, FR-010, SC-004 |
| 4 | `lss sync`, then check email | One "Already on the channel" email for Oct 9. The Oct 9 livestream is untouched in Studio. | Clarification 1 |
| 5 | Calendar: "Funeral for Jane Doe", next Friday 11:00. `systemctl start livestream-scheduler.service` | An **unlisted** livestream `… - Funeral for Jane Doe`, no bulletin line, and an email with the link in the same run | US2-1, US2-5, FR-007, FR-009a |
| 6 | Add `yt.wording: Celebration of Life` and `yt.years: 1941–2026`, then run | Title and description updated. A "changed" email is **not** sent, because the time didn't change. | US2-2, US2-3 |
| 7 | Move the funeral by one hour, then run | Livestream rescheduled, and one "changed" email | FR-009a |
| 8 | Add an event titled just "Funeral", then run | Not published. Occurrence `failed` with a "needs a name" email. | US2-4, FR-006 |
| 9 | Set `defaults.visibility: public` and run again | Funerals stay **unlisted** | SC-005, clarification 2 |
| 10 | `lss link --date <funeral date> --type funeral` | Prints the youtu.be URL | FR-009 |
| 11 | Delete the funeral from the calendar, then run | Livestream removed, and one "removed" email | FR-009a |

**Calendar lag**: Google's secret iCal address can take hours to show new events. For short-notice funerals, add the event as early as possible, and check `lss occurrences --type funeral` before telling the family to expect a link.
