# Contract: Calendar Feed → Livestream Occurrence Mapping

Input: an RFC 5545 iCalendar document. Only `VEVENT` components are read. `VTODO`, `VJOURNAL` and `VALARM` are ignored. `VTIMEZONE` blocks are honored.

## Inclusion

An instance becomes an occurrence only when **all** of these hold:
1. It is a `VEVENT` with `STATUS` ≠ `CANCELLED`. A cancelled instance counts as removed.
2. `DTSTART` is a **date-time**. Date-only (all-day) events are skipped with a `config check` warning.
3. It passes `calendar.include`: when `summary_prefix` is set, `SUMMARY` must start with it. When `directive: true` is set, the description must contain `yt.stream: yes`.
4. Its start falls in `[now + safety.min_lead_minutes, now + horizon.days]`.
5. It is not excluded by `EXDATE`, and recurrence is expanded per `RRULE`/`RDATE` with `RECURRENCE-ID` overrides applied.

## Identity

- **Recurring event instance** (the master has `RRULE`/`RDATE`, or the component has `RECURRENCE-ID`): `key = UID + "|" + original_start_utc`. `original_start_utc` is `RECURRENCE-ID` for an overridden instance, otherwise the expanded instance's `DTSTART`, in UTC formatted `YYYY-MM-DDTHH:MM:SSZ`.
- **Non-recurring event**: `key = UID`.

Consequences (FR-007, FR-008):

| Calendar change | Effect |
|---|---|
| Edit title, description or visibility directive | Same key, *update* |
| Move a non-recurring event | Same key (`UID`), *update* |
| Move one instance of a series (`RECURRENCE-ID` override) | Same key, *update* |
| Change the whole series' `RRULE` or time | Instances whose original start changed get new keys (*delete + create*). Unchanged instances are kept. |
| Turn a single event into a series, or the reverse | Keys change (*delete + create*) |
| Delete an instance (`EXDATE` / `STATUS:CANCELLED`) or the event | Key disappears, *cancelled* (broadcast deleted) |

## Field mapping

| Broadcast field | Source | Transform |
|---|---|---|
| `snippet.title` | `SUMMARY` | Strip `summary_prefix`, trim, collapse whitespace, truncate to 100 chars (warning). Empty → `failed: "Event has no title"`. |
| `snippet.description` | `DESCRIPTION` | HTML → text (Google exports HTML), remove directive lines, remove `<` `>`, cap at 5000 UTF-8 bytes (warning) |
| `snippet.scheduledStartTime` | instance start | Convert to UTC, RFC 3339 |
| `snippet.scheduledEndTime` | instance end (`DTEND`, or `DTSTART`+`DURATION`) | Convert to UTC. If missing, `DTSTART` + 1 h. |
| `status.privacyStatus` | `yt.visibility` directive, else `defaults.visibility` | |
| `status.selfDeclaredMadeForKids` | `defaults.made_for_kids` | |
| `contentDetails.enableAutoStart/Stop/Dvr` | defaults | |

Time-zone handling (FR-014): `TZID` times use that zone. Floating times use `defaults.timezone`. UTC (`Z`) times stay UTC. Recurrences are expanded in **local wall-clock time** of the event's zone, so a "Tuesdays 7 pm New York" stream stays at 7 pm local across DST changes, and its UTC time shifts.

## Description directives

Directives are lines of the form `yt.<name>: <value>`. Names are case-insensitive and whitespace around the colon is ignored. They are removed from the published description.

| Directive | Values | Effect |
|---|---|---|
| `yt.visibility` | public \| unlisted \| private | Per-event visibility override |
| `yt.stream` | yes | Marks the event for inclusion when `include.directive: true` |
| `yt.allow-overlap` | yes | Permit overlap with another occurrence (R11) |

An unknown `yt.*` directive produces a warning and is still removed.
