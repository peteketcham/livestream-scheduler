# Feature Specification: Taizé Services and Funerals

**Feature Branch**: `004-taize-funeral-services`

**Created**: 2026-10-08

**Status**: Draft

**Input**: User description: "taize services should be planned for and modelled as well. funerals should be planned for-- although they won't necessarily show up on the calendar far in advance, a generic template would be useful."

**Depends on**:
- [001](../001-youtube-livestream-scheduler/spec.md): scheduling, calendar source, updates, notifications.
- [002](../002-description-templates/spec.md): templates and snippets.
- [003](../003-lectionary-service-metadata/spec.md): church-service detection, title templates, shared footer, and the evidence in [003 reference](../003-lectionary-service-metadata/reference/sunday-examples.md).

## Clarifications

### Session 2026-10-08

- Q: How are short-notice funerals entered? → A: On the stream calendar only, like every other service. There is no separate entry path.
- Q: Should Taizé services be planned from a rule in the application? → A: No. Calendar only. Taizé livestreams come from calendar events, usually a recurring series.
- Q: What happens when a livestream created by hand already exists at the same time as a calendar event? → A: It is never touched. No duplicate is created, and the owner is told once. Any fix is made by hand on the platform. There is no adopt or take-over mechanism.
- Q: How does the deceased person's name appear in the title and description? → A: Exactly as the volunteer enters it, normally the full name. The livestream is **unlisted by default, never public** unless the volunteer explicitly sets public on that event.
- Q: Should the app email a funeral's watch link automatically? → A: Yes. It emails the owner's notification address as soon as the funeral livestream is created, and again if its date or time changes. The app never emails families.

## Context: what the channel shows today

From the @minnehahaumc livestream history, captured 2026-10-08:
- **Taizé**: Friday evening prayer services.
  - `April 10th Taize`: started 6:55 PM Central and ran 65 minutes. Description: "Welcome to Minnehaha United Methodist Church on April 10th 2026 Taize!" plus the standard footer.
  - `October 9th, 2026 - Taizé`: upcoming, 7:00 PM Central. It was created by hand, and its description is a copy of the Oct 4 Sunday description, with the wrong date and "nineteenth Sunday after Pentecost".
  - The title format and spelling ("Taize" vs "Taizé") are inconsistent.
- **Funerals**: none are visible in the public history. The channel does carry other non-Sunday events that name a person ("Eagle Court of Honor - Cullan F").
- **Shared description footer** (003): a bulletin link that always points to the current Sunday bulletin, the church links, and the music-licensing block.

## Service types

This feature extends 003's yes/no "church service" idea into **service types**. Each type has its own way of being recognized and its own title template, description template, default visibility and default length:

| Type | Typical timing | Lectionary values? | Default visibility |
|---|---|---|---|
| Sunday worship (003) | Sunday morning | Yes | Public |
| Taizé | Friday evening, roughly monthly | No | Public |
| Funeral / memorial | Any day, short notice | No | Unlisted |
| Other | Anything else | No | As 001 default |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Taizé services are recognized and titled consistently (Priority: P1)

The media volunteer puts the Taizé prayer service on the stream calendar as usual. The application recognizes it as a Taizé service and schedules the livestream with a consistent title (`October 9th, 2026 - Taizé`) and a description written for Taizé. It never carries a Sunday description by mistake.

**Why this priority**: Taizé services already happen and are streamed. Today they are created by hand with inconsistent titles and copied Sunday descriptions. This is the most frequent case after Sunday worship.

**Independent Test**: Put a Friday 7:00 PM "Taizé" event on the calendar. Run the scheduler. Confirm the livestream's title and description follow the Taizé format, and that nothing in them refers to a Sunday or a liturgical day.

**Acceptance Scenarios**:

1. **Given** a calendar event titled "Taizé" (or "Taize") on Friday, October 9, 2026 at 7:00 PM, **When** the scheduler runs, **Then**:
   - the title is exactly `October 9th, 2026 - Taizé`;
   - the description's first line is exactly `Welcome to Minnehaha United Methodist Church on October 9th, 2026 for Taizé prayer!`;
   - the rest of the description is the standard church footer.
2. **Given** a Taizé event, **When** its livestream is rendered, **Then** no Sunday-specific values (liturgical day, readings, Sunday bulletin wording) appear unless the owner's Taizé template asks for them.
3. **Given** a recurring Taizé series on the calendar, **When** the scheduler runs, **Then** every instance within the scheduling horizon is scheduled with its own date in the title.
4. **Given** a Taizé livestream for the same date and time that already exists on the channel, created by hand (like the current Oct 9 one), **When** the scheduler first runs, **Then** it does not create a duplicate. It reports the existing livestream so the owner can decide.

---

### User Story 2 - Short-notice funerals with a ready-made template (Priority: P2)

When a funeral or memorial service is arranged, often only days ahead, the media volunteer adds it with the deceased person's name and the service time. The application promptly schedules an **unlisted** livestream with a respectful, consistent title and description. The volunteer can send the link to the family right away.

**Why this priority**: Funerals are less frequent than Taizé, but they are time-sensitive and emotionally important. Getting the wording right under pressure is where a generic template helps most.

**Independent Test**: Enter a funeral for "Jane Doe" two days from now at 11:00 AM. Confirm an unlisted livestream exists within the promised time, with the funeral title format, the person's name, and a description that leaves out the Sunday bulletin. Confirm the link can be read back from the activity view.

**Acceptance Scenarios**:

1. **Given** a funeral entered for Jane Doe on Friday, October 23, 2026 at 11:00 AM, **When** it is processed, **Then**:
   - the livestream's title is exactly `October 23rd, 2026 - Funeral for Jane Doe`;
   - its visibility is **unlisted**;
   - its description begins `Welcome to Minnehaha United Methodist Church on October 23rd, 2026 for the funeral of Jane Doe.`
2. **Given** the family prefers "Memorial Service" or "Celebration of Life", **When** the volunteer sets that on the event, **Then** the title and welcome line use that wording instead of "Funeral" (e.g. `October 23rd, 2026 - Celebration of Life for Jane Doe`).
3. **Given** optional details are provided (years of life, an obituary link, memorial-gift wording), **When** the livestream is rendered, **Then** each provided detail appears in its section of the description, and missing ones are omitted cleanly.
4. **Given** a funeral entered without a person's name, **When** it is processed, **Then** no livestream is created. The volunteer is told the name is required.
5. **Given** a funeral has been scheduled, **When** the livestream is created, **Then** the owner's notification address receives an email with the watch link, and the link can also be shown on request.
6. **Given** a funeral is added to the stream calendar, **When** the entry reaches the application's copy of the calendar, **Then** the livestream exists within the time promised in SC-002. If the volunteer can't wait for the regular cycle, they can request an immediate run (001 `sync`), and that run picks up the calendar entry as soon as the calendar provider publishes it.

---

### User Story 3 - Owner can adjust each service type (Priority: P3)

The owner can change how each service type is recognized (keywords, day and time) and each type's templates, default visibility, and default length. They can also add a new type later, such as a wedding or a concert, without code changes.

**Why this priority**: The defaults cover today's needs. Adjustability protects against wording or schedule changes.

**Independent Test**: Change the Taizé welcome wording and add a "Wedding" type with its own keyword and template. Preview upcoming events and confirm both changes are applied.

**Acceptance Scenarios**:

1. **Given** the owner edits the Taizé description template, **When** the scheduler next runs, **Then** all upcoming Taizé livestreams managed by the application are updated (per feature 002).
2. **Given** the owner defines a new type with a keyword and templates, **When** a matching event appears, **Then** it is rendered with that type's templates.

---

### Edge Cases

- **Taizé spelled "Taize"**, any capitalization, or "Taizé Prayer": all are recognized as Taizé. The published title always uses the church's chosen spelling, "Taizé".
- **Taizé on a Sunday morning**: an explicit type on the event wins over the Sunday-morning default (003 clarification 1). Without one, a title keyword ("Taizé") wins over the Sunday rule.
- **More than one rule matches** (e.g. "Funeral" on a Sunday morning): the precedence is explicit type, then title keyword, then day and time rule, then other.
- **Funeral names**: a name with accents, apostrophes or hyphens (e.g. "José O'Brien-Smith") is published exactly as entered. Characters the platform forbids are removed with a warning (002 FR-009).
- **A long name makes the title too long**: the wording ("Celebration of Life for") is shortened to "Funeral for" or "Memorial for" first. The person's name is never truncated mid-name. If it still does not fit, the date part is shortened (`Oct 23, 2026`), with a warning.
- **A funeral is postponed or cancelled**: moving or deleting it updates or removes the livestream (001 FR-008). If the family asks for the recorded stream to be taken down after the service, that is done manually on the platform. The application never touches it afterward (001 FR-009 and manual-change rules).
- **A manually created livestream already exists at the same start time** (cut-over from today's manual process): the application does not create a duplicate. The occurrence is marked as "already on the channel (created manually)", and the owner is told once. This applies to every type, not only Taizé.
- **The Sunday bulletin link on non-Sunday services**: the funeral description omits it, because it points to the Sunday bulletin. The Taizé description keeps the full footer, as it does today. The owner can change both.
- **Music licensing at funerals**: the licensing block stays, because the same music permissions apply. The owner can remove it per type.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST classify every occurrence as exactly one **service type**. The defaults are: Sunday worship (003), Taizé, Funeral/memorial, and Other.
- **FR-002**: System MUST determine the type in this order of precedence:
  1. an explicit type on the calendar event or series;
  2. a title keyword match (Taizé: "Taizé" or "Taize"; Funeral: "Funeral", "Memorial", "Celebration of Life");
  3. a day and time rule (Sunday worship: Sunday before noon, per 003);
  4. otherwise, Other.

  003's yes/no church-service marker becomes the shorthand for "Sunday worship".
- **FR-003**: Each service type MUST have its own:
  - title template and description template (002);
  - default visibility;
  - default length when the calendar event has none;
  - flag for whether lectionary values are looked up.

  Only Sunday worship looks up lectionary values by default.
- **FR-004**: System MUST ship default Taizé templates that produce:
  - Title: `<Month> <ordinal day>, <year> - Taizé`.
  - Description: the welcome line `Welcome to Minnehaha United Methodist Church on <date> for Taizé prayer!`, followed by the standard church footer (bulletin, links, licensing).
- **FR-005**: System MUST ship default funeral templates that produce:
  - Title: `<Month> <ordinal day>, <year> - <Service wording> for <Name>`.
  - Description: `Welcome to Minnehaha United Methodist Church on <date> for the <service wording, lower-case> of <Name>.`, then optional sections for years of life, obituary link and memorial-gift wording, then the church links and licensing. It omits the Sunday bulletin line.
- **FR-006**: Funeral events MUST carry the deceased person's name. They MAY carry:
  - a service wording ("Funeral" by default; "Memorial Service" or "Celebration of Life");
  - years of life;
  - an obituary link;
  - memorial-gift wording.

  A funeral without a name MUST NOT be published, and the volunteer MUST be told why.
- **FR-006a**: The deceased person's name MUST be published exactly as entered, normally the full name, in both the title and the description. There is no abbreviation or reformatting, apart from removing characters the platform forbids.
- **FR-007**: Funeral livestreams MUST default to **unlisted** visibility. They MUST NOT be public unless the volunteer explicitly sets public on that specific event. The configured visibility default for other types MUST NOT apply to funerals. A visibility setting on a recurring series does not apply either, because funerals are single events.
- **FR-008**: Funerals MUST be entered on the stream calendar like any other service, with no separate entry path. System MUST schedule them within the time in SC-002, and MUST let the volunteer trigger an immediate run instead of waiting for the next regular one.
- **FR-009**: System MUST show the watch link of any scheduled livestream on request, so it can be shared with a family or group.
- **FR-009a**: When a funeral livestream is created, System MUST email its watch link, title, date, time and visibility to the owner's notification address. It MUST send an updated email if the funeral's date or time changes, and a removal notice if it is cancelled. These are one-time messages per change, not reminders. System MUST NOT email anyone else (families are contacted by the church office).
- **FR-010**: System MUST NOT create a livestream when a livestream not created by the application already exists on the channel within 15 minutes of the same start time. It MUST mark the occurrence as already present and notify the owner once, naming the existing livestream. It MUST NOT modify, adopt or take over that livestream; any fix is made by hand on the platform. This also covers the cut-over from manual scheduling. If the livestream created by hand is later deleted, the occurrence becomes eligible again, and the application creates its own livestream on the next run.
- **FR-011**: The standard church footer MUST be made of separately reusable parts (bulletin line; links; music licensing), so each service type can include or omit each part.
- **FR-012**: The owner MUST be able to change each type's recognition rules, templates, visibility and default length, and to add new types, through configuration and template files alone.
- **FR-013**: A recurring Taizé series on the calendar MUST be scheduled like any other recurring series (001). Each instance's title carries its own date.

### Key Entities

- **Service Type**: A named kind of service (Sunday worship, Taizé, Funeral, Other, or owner-added). Attributes:
  - recognition rules (keywords, day/time window)
  - title and description templates
  - default visibility and length
  - whether lectionary values are used
  - which footer parts are included
- **Funeral Details**: Per-event values for a funeral: deceased's name (required), service wording, years of life, obituary link, memorial-gift wording.
- **Footer Parts**: Bulletin line, church links, music licensing. These are reusable snippets (002).
- **Existing Channel Livestream**: A livestream already on the channel that the application did not create. It is consulted only to avoid duplicates (FR-010) and never modified.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of Taizé livestreams scheduled by the application have the title format `<date> - Taizé` and a Taizé description. 0 have a Sunday description.
- **SC-002**: A funeral entered on the calendar at least 24 hours ahead has an unlisted livestream and a shareable link within 1 hour of the entry appearing in the calendar feed, or within minutes if the volunteer triggers an immediate run.
- **SC-003**: Once the funeral is in the calendar feed, the shareable link arrives by email within the same run that creates the livestream. A volunteer who triggers a run has it in under 5 minutes.
- **SC-004**: 0 duplicate livestreams are created for services that were already scheduled by hand before the application took over.
- **SC-005**: 0 funeral livestreams are published as public unless the volunteer chose public for that event.
- **SC-006**: Adding a new service type (e.g. weddings) takes under 15 minutes and needs no code change.

## Assumptions

- Taizé services come only from the stream calendar, usually as a recurring event (e.g. the second Friday of the month at 7:00 PM, matching April 10 and October 9, 2026). The application never invents Taizé services from a rule of its own. Skipped or moved months are handled by editing the calendar.
- Funerals also come only from the calendar. Calendar providers can take hours to publish changes to subscribed feeds (Google's published calendar address in particular, per 001 research). For short-notice funerals, the volunteer should add the event as early as possible. Using a calendar whose feed updates quickly is recommended.
- The funeral's details (name, service wording, years, obituary link, memorial-gift wording) are written in the calendar event using the per-event settings mechanism from 001.
- "Taizé prayer" is the default welcome wording, chosen because the church's own text is inconsistent ("April 10th 2026 Taize!"). The owner can change it.
- Funeral wording defaults are respectful and neutral. The church office or pastor confirms the family's preferred wording before entry. The application does not contact families.
- The family has agreed to livestreaming and to the name appearing in the title. Getting that consent is outside the application.
- Thumbnails, chat settings and the removal of recordings after funerals are out of scope (001 assumption). Removal is done manually on the platform.
- Weddings, concerts and other events (e.g. "Eagle Court of Honor") use the "Other" type and 001/002 behavior until the owner adds a type for them (FR-012).
- The 15-minute window for detecting existing livestreams (FR-010) covers small start-time differences such as 6:55 vs 7:00 PM.
