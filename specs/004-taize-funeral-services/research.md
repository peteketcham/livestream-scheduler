# Phase 0 Research: Taizé Services and Funerals

**Feature**: `004-taize-funeral-services` | **Date**: 2026-10-08

This builds on [001](../001-youtube-livestream-scheduler/research.md) (R1–R16) and [003](../003-lectionary-service-metadata/research.md) (T1–T6, L1–L10). Decisions are numbered **S**.

Evidence: the channel history, captured 2026-10-08, in [003 reference](../003-lectionary-service-metadata/reference/sunday-examples.md#channel-history-titles-captured-2026-10-08-from-the-channels-live-tab).

---

## S1. Service-type registry (FR-001, FR-002, FR-003, FR-012)

- **Decision**: An ordered list `service_types` in config. Each entry has an `id`, `match` rules, templates, visibility, default duration, a `lectionary` flag, and type options. The bundled defaults are `worship`, `taize`, `funeral` and `other`; `other` is implicit and always last. The full schema is in [contracts/service-types.md](contracts/service-types.md).
  - Classification is a pure function, `classify(event, instance) → (type_id, reason)`. It applies precedence: **directive** (`yt.type: <id>`; 003's `yt.service: yes|no` is kept as an alias for `worship` / `other`), then **title keyword**, then **day/time rule**, then `other`.
  - Within a precedence level, the first matching entry in registry order wins.
  - **Keyword matching** normalizes the title (Unicode NFKD, accents stripped, casefolded) and matches whole words. `Taize`, `TAIZÉ` and `Taizé Prayer` all match `taize`. "Memorial" does not match inside "Memorials Committee", because it isn't a whole word.
  - 003's service detection (L7: the Sunday-before-noon rule and the Saturday-vigil rule) becomes the `worship` entry's `match.when` rule. The 003 config keys `service.sunday_cutoff`, `service.saturday_vigil_after`, `service.title_template` and `service.description_template` move under `service_types[worship]`. `service.church_name` and `service.no_article_names` stay global.
- **Rationale**: Adding a type such as weddings takes config and template files only (FR-012, SC-006). One code path handles every type. The worship type keeps 003's behavior exactly.
- **Alternatives considered**:
  - Hard-coded `if taize … elif funeral` branches were rejected because they fail FR-012.
  - Per-calendar routing (one calendar per type) was rejected because the owner uses a single stream calendar.

## S2. Funeral details: entry and validation (FR-005, FR-006, FR-006a)

- **Decision**:
  - Details are read from the calendar event using the 001 directive mechanism: `yt.name`, `yt.wording`, `yt.years`, `yt.obituary`, `yt.memorials`.
  - **Name fallback from the title**: if `yt.name` is absent, the name is taken from the event title when it matches `<keyword> (for|of|:|–|-) <Name>`. For example, "Funeral for Jane Doe" and "Celebration of Life – José O'Brien-Smith" both work.
  - The name is used **exactly as entered**: trimmed and whitespace collapsed, with nothing else changed. Only `<` `>` are removed, with a warning (FR-006a).
  - `yt.wording` sets the service wording; the default is `Funeral`.
- **Required values**: a type declares `requires: [funeral.name]`. A missing required value makes the occurrence `failed` with the reason `Funeral needs a name: add "yt.name: …" to the event notes or title it "Funeral for <name>"`, and the owner is notified. Nothing is published (FR-006).
- **Rationale**: Volunteers naturally title the event "Funeral for Jane Doe", so taking the name from the title removes a step. The directive stays available for unusual titles.

## S3. Title fitting via template fallbacks (spec edge case: long names; also 003's parenthetical rule)

- **Decision**: `title_template` may be a **list**. Candidates are rendered in order, and the first one that is ≤ 100 characters is used. Each step down adds a warning. If none fits, the last candidate is cut at a word boundary (002 T4).
  - **Funeral**, three candidates:
    1. `<date_long> - <Wording> for <Name>`
    2. The same with the wording shortened to `Funeral` or `Memorial`.
    3. `<date_short> - <Funeral/Memorial> for <Name>`, where `date_short` is `Oct 23, 2026`.
  - The name is never cut, as long as some candidate fits.
  - 003's "drop the parenthetical" rule becomes the `worship` list `[service-title, service-title-no-special]`, which is the same behavior expressed generically.
- **Rationale**: One mechanism covers both features, and the shortening steps are visible in the template files.

## S4. Funeral visibility lock (FR-007)

- **Decision**: The type option `visibility_source: instance_only` (set for `funeral`) means:
  - visibility is the type's `visibility` (`unlisted`) unless a `yt.visibility` directive appears **on that event instance itself**;
  - series-level directives and `defaults.visibility` are ignored;
  - a `yt.visibility: public` on a funeral is honored, with an info message in the run log ("funeral published as PUBLIC by event setting").
- **Test**: a funeral under every combination of defaults, series directives and instance directive is only public when the instance says so (SC-005).

## S5. Funeral link email (FR-009a)

- **Decision**: The type option `announce: true` (set for `funeral`) triggers an email to `notify.email_to` after the insert is **committed**. Subject: `[livestream-scheduler] Funeral livestream scheduled: <title>`. The body has the watch URL (`https://youtu.be/<id>`), the local date and time, the visibility, and the calendar event title. Further emails:
  - **changed**: when a later run updates the start time or date of an announced occurrence;
  - **cancelled**: when the broadcast is deleted because the event left the calendar.

  Deduplication uses the 001 `notification` table, with the key `announce:<occurrence_id>:<kind>:<start_utc>`. Each kind is sent exactly once per distinct start time, and there are no reminders.
  - If the email fails (SMTP down), the key stays unsent and is retried on the next run. Failure to announce never blocks scheduling.
- **Rationale**: The link is what the family needs, and the email fires in the same run that creates the livestream (SC-003). Recipients are limited to the owner (clarification 3).

## S6. Livestreams created by hand: duplicate prevention (FR-010; applies to 001)

- **Decision**: A new 001 planner step, **external-conflict check**:
  - It runs only when the plan contains at least one `create`. It calls `YouTubePort.list_upcoming()` once per run (`mine=true`, `broadcastStatus=upcoming`, 1 quota unit per 50 results).
  - Any upcoming broadcast **not** in the `broadcast` table whose `scheduledStartTime` is within ±15 min of a pending occurrence's start blocks that create. The occurrence moves to the new state **`exists_external`**, with `external_broadcast_id` and `external_title` recorded. The owner gets one notification (`problem_key=external:<occurrence_id>`) naming the livestream and its link.
  - **Never modified**: the external id is never written to `broadcast`, so 001's ownership rule ("only ids from `broadcast` are ever updated or deleted") keeps it untouchable. That satisfies clarification 1 (no adopt).
  - **Re-check**: on each later run, `exists_external` occurrences are re-checked in the same listing. If the external broadcast is gone (deleted, or already live and complete) and the occurrence is still in the future, it goes back to `pending` and is created normally (spec FR-010 last sentence).
  - **Interaction with 001 R5 crash recovery**: R5 adoption applies only to occurrences in `creating`, with `publishedAt ≥ intent_at`. Livestreams created by hand are older than any intent, so the two paths cannot be confused.
- **Concrete case**: the existing hand-made `October 9th, 2026 - Taizé` at 00:00 UTC Oct 10 matches the calendar's Friday 7:00 PM Taizé. The occurrence becomes `exists_external`, there is no duplicate, and one email is sent.
- **Alternatives considered**:
  - Matching on title similarity was rejected: titles created by hand are inconsistent ("April 10th Taize").
  - A wider window was rejected: ±15 min covers the observed 6:55 vs 7:00 PM difference without catching neighboring services.

## S7. Footer split into reusable parts (FR-011)

- **Decision**: The single 003 snippet becomes three parts plus a wrapper, with byte-identical output for Sunday worship (003 SC-001a still holds):
  - `snippets/bulletin.txt.j2`
  - `snippets/links.txt.j2`
  - `snippets/licensing.txt.j2`
  - `snippets/minnehaha-footer.txt.j2`, which includes all three with the original blank lines between them

  The Taizé template includes the full footer (current practice). The funeral template includes links and licensing only, with no Sunday bulletin. Exact text is in [contracts/templates.md](contracts/templates.md).

## S8. Taizé wording and defaults (FR-004, FR-013)

- **Decision**:
  - Title: `<date_long> - Taizé`, spelled with the accent everywhere, matching the newest channel title.
  - Welcome line: `Welcome to Minnehaha United Methodist Church on <date_long> for Taizé prayer!`
  - Visibility: public. Default duration: 65 min (observed). No lectionary lookup.
  - A recurring Taizé series works through 001's normal series expansion. There is no Taizé-specific scheduling rule (clarification 2).

## S9. Immediate run and link lookup (FR-008, FR-009)

- **Decision**:
  - **Immediate run**: `sudo systemctl start livestream-scheduler.service`, the same unit as the timer. Or `lss sync`, which uses the same lock. The quickstart documents both.
  - **New command** `lss link <occurrence-id> | --date YYYY-MM-DD [--type funeral]` prints the watch URL. `lss occurrences --type <id>` filters by service type ([contracts/cli-additions.md](contracts/cli-additions.md)).
- **Calendar lag**: unchanged from 001 R1. The quickstart warns that Google's secret ICS address can lag for hours, and suggests adding funerals as early as possible.

## S10. Testing additions

- **Unit**:
  - classification precedence, accent and word-boundary matching, alias `yt.service`;
  - funeral name extraction (title patterns, directive wins, unicode names);
  - funeral visibility matrix (S4);
  - title fallback selection (S3).
- **Golden**:
  - Taizé Oct 9, 2026;
  - funeral Jane Doe Oct 23, 2026 (all wordings);
  - a long-name funeral exercising every fallback;
  - Sunday worship output unchanged after the footer split.
- **Integration**:
  - a hand-made Taizé already on the fake channel leads to `exists_external` and no insert. Deleting it leads to the app creating its own on the next run.
  - funeral create → one email; move → "changed" email; delete → "cancelled" email; repeated runs → no more emails.
