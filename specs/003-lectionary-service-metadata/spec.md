# Feature Specification: Lectionary-Based Titles and Descriptions for Church Services

**Feature Branch**: `003-lectionary-service-metadata`

**Created**: 2026-10-08

**Status**: Draft

**Input**: User description: "if it's a church service, there are title/description fields that can be populated from information on https://www.umcdiscipleship.org/calendar/lectionary directly."

**Depends on**:
- [001-youtube-livestream-scheduler](../001-youtube-livestream-scheduler/spec.md): scheduling, updates, manual-edit respect, run records, notifications.
- [002-description-templates](../002-description-templates/spec.md): templates and template values.

This feature adds a new source of template values for church services and extends templating to titles.

## Clarifications

### Session 2026-10-08

- Q: Which calendar events are automatically treated as church services? → A: Any event starting on a Sunday before 12:00 noon (local time) is a service by default. Any event can opt in, and a Sunday-morning event can opt out, with a line in its notes.
- Q: When a Sunday also has a special name (e.g. All Saints Sunday), what does the title show? → A: The regular liturgical day followed by the special name in parentheses, e.g. `November 1st, 2026 - Twenty-Third Sunday after Pentecost (All Saints Sunday)`.

## Amendments from planning research (2026-10-08)

Planning examined the site's full lectionary calendar export (412 entries, Oct 2019 – Dec 2026) and its pages. The details are in [research.md](research.md) L1–L3. The site's day names are **inconsistent** across years:
- The same Sunday is sometimes named by its number ("Twenty-Third Sunday after Pentecost") and sometimes by its special name ("All Saints Sunday").
- Capitalization varies ("After" vs "after", "year B").
- Some names carry extras ("Easter Sunday 2026").
- Names for upcoming dates can change once the site publishes planning material.

The site's "Special Sundays" calendar lists nothing for the next six months. These facts led to the amendments below:
1. **Liturgical day name, lectionary year, and season are worked out by the application** from the standard lectionary calendar rules. Dates and Easter are deterministic. The site is used to cross-check these values, not as their source. Titles are therefore always available, are consistent, and never change because the site renamed a day.
2. **Readings, liturgical color, worship series and week titles, and the planning-page link still come from the site**, as before.
3. **Special-day names** (for the parenthetical decided in Clarifications) come from an owner-editable list of observed special days. By default the list holds All Saints Sunday (the first Sunday in November) and Reign of Christ / Christ the King Sunday (the Sunday before Advent). World Communion Sunday is deliberately **not** in the default list, because the church's own Oct 4, 2026 title omitted it.

4. **The church's own naming wins** where its history differs from the standard names: "Pentecost" (not "Day of Pentecost") and "First Sunday after Pentecost" (not "Trinity Sunday"). These are owner-editable name aliases. Titles may carry a per-event **extra** ("Easter Sunday with the band"). Evidence: the channel's livestream history, in [reference/sunday-examples.md](reference/sunday-examples.md).

## Context: what the source provides

The Discipleship Ministries lectionary calendar (umcdiscipleship.org) lists upcoming Sundays and special days about five weeks ahead. Each entry gives the liturgical day name with its lectionary year, for example "Twenty-First Sunday after Pentecost, Year A", and the date. It links to a worship-planning page for that day. As of 2026-10-08, a worship-planning page provides:
- the liturgical day name and date
- the **scripture readings** (e.g. Exodus 33:12-23; Psalm 99; 1 Thessalonians 1:1-10; Matthew 22:15-22)
- the **liturgical color** (e.g. Green)
- the **worship series title** (e.g. "Always Give Thanks") and the **week's title** (e.g. "Chosen")
- a prose **theme summary**
- a copyright notice ("© Discipleship Ministries. All Rights Reserved")

## Context: the church's current livestream format

The owner provided two recent Minnehaha UMC Sunday livestreams as the model for templated Sundays. They are captured verbatim in [reference/sunday-examples.md](reference/sunday-examples.md). In summary:
- **Title**: `October 4th, 2026 - Nineteenth Sunday after Pentecost`. The format is date with ordinal day, then " - ", then the liturgical day name without the lectionary year.
- **Description**:
  - A welcome line that repeats the date and liturgical day.
  - A fixed bulletin link.
  - Fixed website and social links.
  - A fixed music-licensing block (ONE LICENSE, CCLI, CCS).
- Only the date and the liturgical day change from week to week. Readings, color, and series titles are not currently shown.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Church service livestreams get the liturgical day in their title and description (Priority: P1)

A church's media volunteer schedules the weekly Sunday worship livestream as a recurring calendar event. Each week's livestream is titled with that Sunday's liturgical day name, such as "Twenty-First Sunday after Pentecost", in the church's established format. The description's welcome line names the same day. Nobody has to look this up and type it each week.

**Why this priority**: This is the whole request. Weekly retyping of the date and liturgical day is the repetitive chore the feature removes.

**Independent Test**: Mark a weekly Sunday calendar series as a church service. Run the scheduler. Confirm each upcoming Sunday livestream's title and welcome line contain the correct liturgical day name for that date.

**Acceptance Scenarios**:

1. **Given** a weekly Sunday 9:30 AM event marked as a church service and the default Minnehaha UMC templates, **When** the scheduler creates the livestream for Sunday October 18, 2026, **Then**:
   - the title is exactly `October 18th, 2026 - Twenty-First Sunday after Pentecost`;
   - the description's first line is exactly `Welcome to Minnehaha United Methodist Church on October 18th, 2026 for the Twenty-First Sunday after Pentecost!`;
   - the rest of the description is identical, character for character, to the fixed bulletin, links, and licensing text in the reference examples.
2. **Given** a Sunday that the lectionary calendar also lists as "All Saints Sunday", **When** the livestream is created, **Then** its title is `<date> - <liturgical day> (All Saints Sunday)` and the welcome line uses the same label.
3. **Given** the default templates are rendered for September 27 and October 4, 2026, **When** compared with the two reference livestreams, **Then** titles match exactly. Descriptions match exactly except for the corrected, consistent capitalization of the liturgical day.
4. **Given** the owner adds the readings to the description template, **When** the October 18, 2026 livestream is rendered, **Then** the description lists Exodus 33:12-23, Psalm 99, 1 Thessalonians 1:1-10, and Matthew 22:15-22.
5. **Given** a calendar event *not* marked as a church service, **When** the scheduler runs, **Then** its title and description are produced exactly as without this feature.
6. **Given** a church service livestream, **When** the owner previews it (feature 002), **Then** the preview shows the lectionary values that were used and which lectionary page they came from.

---

### User Story 2 - Use any lectionary detail in templates (Priority: P2)

The owner can place any lectionary value into the title or description templates, in any arrangement. Available values are the liturgical day, lectionary year, season, liturgical color, readings, worship series title, week title, and the link to the planning page. For example: "Week 1 of our series *Always Give Thanks*: Chosen".

**Why this priority**: The default layout in Story 1 covers most churches. Custom arrangements are a refinement.

**Independent Test**: Write a description template that uses the series title, week title, color, and readings, then preview a service. Confirm every value matches the lectionary site for that date.

**Acceptance Scenarios**:

1. **Given** a template that uses the series title and week title, **When** a service falls on a Sunday that belongs to a worship series, **Then** both appear in the rendered text.
2. **Given** the same template, **When** a service falls on a Sunday with no worship series, **Then** the template's "only if present" sections are omitted cleanly. No blank labels or placeholder text appear.

---

### User Story 3 - Owner overrides for a specific service (Priority: P3)

Sometimes the church departs from the lectionary, for example a guest preacher, a special Sunday, or a different text. The owner can override any lectionary value, or the whole title or description, for one service from the calendar event. The override always wins.

**Why this priority**: This is uncommon but necessary for trust. Without it, the owner would have to stop marking that week as a service.

**Independent Test**: Override the readings and the title on one week's calendar instance. Confirm only that week's livestream uses the overrides, and other weeks still use the lectionary.

**Acceptance Scenarios**:

1. **Given** a per-event override of the readings, **When** the scheduler runs, **Then** that service's description shows the overridden readings and all other lectionary values are unchanged.
2. **Given** a per-event full title override, **When** the scheduler runs, **Then** the title is exactly the override text.

---

### Edge Cases

- **Sunday-morning event that is not worship** (for example, an early concert): it gets lectionary titles unless it is opted out. The preview (US1-6) makes this visible before it is published.
- **Sunday event at or after noon**: not a service unless it is opted in.
- **Service not on a Sunday** (it must be opted in):
  - A service on a date the lectionary lists, such as Christmas Eve, Ash Wednesday or Good Friday, uses that date's entry.
  - A Saturday-evening service uses the following Sunday's entry by default. This can be configured.
  - Any other date with no entry is treated as "lectionary data not available".
- **Special day** (a date in the owner's list of observed special days, for example All Saints Sunday): the **service label** is the regular liturgical day followed by the special name in parentheses, e.g. "Twenty-Third Sunday after Pentecost (All Saints Sunday)". The label is used in both the title and the welcome line. If there are several special names, they are joined with " / " in the order the site lists them. If the title would exceed the platform's title limit, the parenthetical is dropped from the title only (with a warning), and the regular liturgical day is never truncated. Both names remain available as separate template values.
- **Site data not yet published** (the service is further ahead than the site lists, or the planning page is missing): titles are unaffected because the day name is worked out locally. Only templates that use site-only values (readings, color, series) are affected. The livestream is created using the owner's fallback for those parts. When the data appears on a later run, the livestream is updated to the lectionary-based text. This follows the normal update rules, so manual edits on the platform are still respected. The run record shows which services are waiting for lectionary data.
- **Site unreachable, changed layout, or returns incomplete data**: already-published livestreams are never blanked or downgraded to fallback text. The last successfully retrieved values are kept, the problem is recorded, and the owner is notified once per problem (per feature 001's notification rules).
- **Site corrects or changes a value** (e.g. a reading changes): upcoming livestreams that the app manages are updated on the next run.
- **Site data disagrees with the service date** (an entry appears under two different dates, as observed on the site): the entry whose own planning page states the matching date is used. If the conflict cannot be resolved, the value is treated as unavailable and a warning is recorded.
- **Capitalization**: the liturgical day name keeps the site's capitalization ("Nineteenth Sunday after Pentecost") everywhere, including mid-sentence. The hand-typed reference descriptions were inconsistent on this, and the templates make it consistent.
- **Text exceeds platform limits** (titles are especially short): the title and description limit rules from features 001 and 002 apply, with a warning.
- **Lectionary year rollover at Advent**: the year letter (A/B/C) changes on the First Sunday of Advent. It is worked out by the application and cross-checked against the site.
- **Site names a day differently from the application** (e.g. the site's "All Saints Day" vs the application's "Twenty-Third Sunday after Pentecost"): the application's name is used, and the difference is recorded for information. If the site's **year letter or date** disagrees, a warning is recorded and the owner is notified once, because that suggests an error on one side.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST treat every event that starts on a Sunday before 12:00 noon, in the event's local time, as a church service by default. Any event, on any day or time, MUST be markable as a service (opt in) with a line in its calendar notes. A Sunday-morning event MUST be excludable (opt out) the same way. Opt-in and opt-out apply to a whole recurring series when set on the series. The noon cutoff is configurable.
- **FR-002**: For each church service occurrence, applying the Saturday-evening rule in Edge Cases, System MUST:
  - **work out** the liturgical day name, lectionary year, and season from the standard lectionary calendar rules. The name has no year suffix, no series prefix, and consistent capitalization, as in the church's titles.
  - **retrieve** from the Discipleship Ministries lectionary site, when available, that date's readings, liturgical color, worship series title, week title, and planning-page link.
  - **take** the special-day name, if any, from the owner's list of observed special days.

  The values available per occurrence are:
  - liturgical day name
  - lectionary year
  - liturgical season
  - liturgical color
  - scripture readings
  - worship series title
  - week title
  - the link to the worship-planning page
  - any special-day name
  - the service label: the liturgical day, plus the special-day name(s) in parentheses when present
- **FR-003**: System MUST make every value in FR-002 available as a template value for both titles and descriptions. Missing values MUST be reported as absent, so templates can omit them cleanly.
- **FR-004**: System MUST support a **title template** for church services, using the same template capabilities as feature 002's description templates. This extends templating to titles, which feature 002 left out of scope.
- **FR-005**: System MUST ship default church-service title and description templates that reproduce the Minnehaha UMC format in [reference/sunday-examples.md](reference/sunday-examples.md):
  - Title: `<Month> <ordinal day>, <year> - <service label>`. The service label is the liturgical day, plus ` (<special name>)` when the date has one.
  - Description: the welcome line, then the bulletin link, website and social links, and music-licensing block.
  - The fixed blocks are maintained as shared snippets, so a license number or link can be changed in one place.
  - The owner can replace either template.
- **FR-006**: When a template uses site-only values (readings, color, series, week title, link) that are not yet available, the "only if present" sections are omitted, or the owner's configured fallback text is used. The livestream is created anyway and updated automatically once the data becomes available. Titles that use only worked-out values (date, day name, special day) never need a fallback.
- **FR-007**: Per-event overrides set in the calendar MUST take precedence over retrieved lectionary values, for individual values and for the whole title or description.
- **FR-008**: System MUST never replace previously published lectionary-based text with fallback or empty text because of a retrieval failure. It MUST keep using the last successfully retrieved values for that date.
- **FR-009**: System MUST retrieve lectionary data no more often than once per day per page under normal operation, plus at most once per run for dates whose data is still missing. It MUST identify itself honestly to the site.
- **FR-010**: By default, System MUST publish only factual reference values: day name, year, season, color, scripture references, series and week titles, and the link. Republishing the site's prose content, such as the theme summary, MUST require the owner to explicitly turn it on. When it is turned on, the source MUST be credited in the description.
- **FR-011**: System MUST record, per service occurrence, which lectionary entry and page were used and when they were retrieved. This MUST be visible in previews and run records.
- **FR-012**: System MUST detect when retrieved data looks wrong: no readings, a date mismatch, or an unrecognizable page. It MUST treat that data as unavailable rather than publish it, and notify the owner.
- **FR-013**: Events not marked as church services MUST be unaffected by this feature.

### Key Entities

- **Observed Special Day**: An owner-editable entry consisting of a name and a date rule (e.g. "All Saints Sunday: first Sunday of November"). It supplies the parenthetical in the service label.
- **Church Service Marker**: Indicates that an occurrence is a church service. It comes from the default Sunday-morning rule, or from an explicit opt-in or opt-out on the event or series. An explicit marker always beats the default rule. It can also carry the church name and a Saturday-evening rule.
- **Lectionary Entry**: One liturgical day as published by the source. Attributes:
  - date
  - liturgical day name
  - lectionary year (A/B/C)
  - season
  - color
  - scripture readings (ordered list of references)
  - worship series title
  - week title
  - planning-page link
  - special-day name
  - retrieval time
  - source page
- **Service Values**: The lectionary values for one service occurrence after applying per-event overrides. These are supplied to title and description templates.
- **Fallback Text**: Owner text used in place of site-only values while they are unavailable.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For services within the period the site has published, 100% of church service livestreams have titles in the church's established format with the liturgical day matching the lectionary site for their date. The owner does no manual entry.
- **SC-001a**: Rendering the default templates for the two reference Sundays (Sept 27 and Oct 4, 2026) reproduces the published titles exactly and the descriptions exactly, apart from the corrected, consistent capitalization of the liturgical day.
- **SC-002**: The weekly time the owner spends on livestream titles and descriptions for regular services drops to zero, apart from deliberate overrides.
- **SC-003**: 0 livestreams are published with empty, blank-labeled, or obviously wrong lectionary text, such as readings from a different date.
- **SC-004**: A livestream created with fallback text is updated to lectionary-based text within one day after the site publishes that date's data.
- **SC-005**: A site outage or layout change causes 0 already-published lectionary titles or descriptions to be blanked or reverted. The owner is notified within one scheduler run.
- **SC-006**: A first-time owner can mark their Sunday service series and see correct lectionary-based previews in under 10 minutes.

## Assumptions

- The church is Minnehaha United Methodist Church, and its channel is @minnehahaumc (channel ID `UCzwZQ34D3RZEncTf6fAe0hQ`). The church's name appears in the welcome line, not the title. The default full name is "Minnehaha United Methodist Church", and the owner can change it.
- Sunday worship is at 9:30 AM Central and lasts about 60–75 minutes. The time comes from the calendar event, as for any other event.
- The bulletin link is a fixed address the church overwrites each week, so it is static text in a snippet, not a per-week value.
- Video category is set on the finished video, not the scheduled event, so it is out of scope.
- The church follows the Revised Common Lectionary as published by Discipleship Ministries (United Methodist Church). Other lectionaries, other denominations' calendars, and other sources are out of scope for this version.
- Only scripture **references** are published, not the scripture text itself.
- The site's calendar export lists day names and dates (about 11 weeks ahead as of 2026-10-08) but no readings, links, or special names. Readings and color appear only on the planning pages, which the listing page links for about the next 5 weeks. Values are read from these public pages, which the site's robots rules permit, and the feature must tolerate layout changes as described in Edge Cases.
- Planning pages cover about 5 weeks ahead, which covers the default 4-week horizon. Because titles are worked out locally, the fallback path only affects optional site-only values.
- Special days are defined by the owner's list. Names the site gives special days are not used automatically, because they change between years and before publication.
- Scripture references and liturgical names are factual and freely usable. The site's prose, such as theme summaries, is copyrighted ("All Rights Reserved"), so republishing it is off by default and is the owner's responsibility when turned on (FR-010).
- Feature 002 is in place, or delivered together with this one, for templating, previews, and snippets. This feature's FR-004 extends title templating to church services. A later change may generalize title templates to all events.
- The per-event settings mechanism from feature 001, lines in the calendar event's notes, is used for the church service marker and per-event overrides.
