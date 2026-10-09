# Feature Specification: Templated Livestream Descriptions

**Feature Branch**: `002-description-templates`

**Created**: 2026-10-08

**Status**: Draft

**Input**: User description: "the descriptions for the events should be from templates-- jinja+markdown maybe?"

**Depends on**: [001-youtube-livestream-scheduler](../001-youtube-livestream-scheduler/spec.md). This feature changes how the description of each scheduled livestream is produced. Everything else about scheduling is unchanged.

**Planned in**: [003 plan](../003-lectionary-service-metadata/plan.md) (research T1–T6). There is no separate 002 plan. Title templating, out of scope here, was brought in by 003 FR-004.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Use a reusable description template for every livestream (Priority: P1)

The owner writes one description template, containing links, a standard call to action, and a sign-off. Every scheduled livestream gets a description built from that template, with the stream's own details filled in: title, date and time, and the notes the owner typed into the calendar event. The owner no longer copies boilerplate into every calendar event.

**Why this priority**: This is the core request. Without a default template applied to every livestream, there is no value.

**Independent Test**: Define a default template that references the stream's title, local start time, and calendar notes. Schedule two different calendar events. Confirm each published livestream description contains the shared boilerplate with that event's details correctly filled in.

**Acceptance Scenarios**:

1. **Given** a default template that includes placeholders for title, start date and time, and event notes, **When** the scheduler creates a livestream for a calendar event, **Then** the published description is the template with every placeholder replaced by that event's values.
2. **Given** no template is configured, **When** the scheduler creates a livestream, **Then** the description is the calendar event's notes, exactly as before this feature.
3. **Given** a template uses light formatting (headings, bullet lists, links, emphasis), **When** the description is published, **Then** it reads cleanly as plain text on the platform. Bullets appear as bullets, links appear as their full web address, and no raw formatting symbols such as `**` or `#` remain.

---

### User Story 2 - Choose different templates for different kinds of streams (Priority: P2)

The owner runs more than one kind of show, such as a weekly Q&A and a monthly deep-dive. Each needs a different description. The owner names templates and picks one per calendar event, or per recurring series. Events that pick nothing use the default.

**Why this priority**: This is common for channels with more than one format, but a single default template already delivers most of the value.

**Independent Test**: Create two named templates. Mark one calendar series to use the second template. Confirm that series' livestreams use it and all other events use the default.

**Acceptance Scenarios**:

1. **Given** two named templates and a calendar series marked to use "deep-dive", **When** the scheduler runs, **Then** every livestream in that series uses the "deep-dive" template and unmarked events use the default.
2. **Given** an event names a template that does not exist, **When** the scheduler runs, **Then** that event's livestream is not published with a broken or empty description. The occurrence is marked failed with a reason naming the missing template, and the owner is notified.

---

### User Story 3 - Preview and update descriptions safely (Priority: P3)

Before anything goes public, the owner can see exactly what each upcoming livestream's description will look like. When the owner edits a template, every upcoming livestream that the application manages and that uses it is updated on the next run.

**Why this priority**: Descriptions are public. Seeing them before they go live, and changing them everywhere at once, builds trust, but it builds on Stories 1 and 2.

**Independent Test**: Preview the rendered description for an upcoming occurrence without contacting the platform. Edit the template, run the scheduler, and confirm all upcoming managed livestreams using it now show the new text.

**Acceptance Scenarios**:

1. **Given** a template and upcoming occurrences, **When** the owner asks for a preview, **Then** the fully rendered description for each chosen occurrence is shown, along with any warnings (for example, too long), and nothing is published.
2. **Given** upcoming livestreams already published from a template, **When** the owner edits the template and the scheduler next runs, **Then** each upcoming livestream managed by the application that uses that template is updated to the new rendered text.
3. **Given** a livestream whose description the owner edited by hand on the platform, **When** the template changes, **Then** that livestream is not overwritten. Manual changes are still respected, as in feature 001.

---

### Edge Cases

- **Template has a syntax error**: no livestream is created or updated using that template. Affected occurrences are marked failed with the template name and the line of the problem. Livestreams that are already published keep their current description. The owner is notified.
- **Template references a value that does not exist** (for example, a misspelled placeholder): this is treated as an error, not silently rendered as blank, so mistakes don't go public.
- **Rendered description exceeds the platform's length limit**: it is shortened at a clean boundary with a warning in preview and in the run record. It is never rejected silently.
- **Rendered description contains characters the platform forbids** (for example, angle brackets): they are removed and a warning is shown.
- **Calendar notes contain formatting or markup from the calendar app**: the notes are converted to plain text before they are inserted into the template.
- **Template file is missing or unreadable at run time**: treated like a syntax error. Nothing is published with that template, and the owner is notified.
- **Date and time placeholders**: always shown in the owner's configured time zone, or the event's own time zone, with a configurable format. Daylight-saving changes are handled correctly.
- **Two occurrences render identical descriptions**: this is allowed. Templates do not have to produce unique text.
- **A template change affects many livestreams at once**: updates count toward the platform's daily usage limit like any other update. Updates that don't fit are retried on later runs, as in feature 001.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let the owner define one or more description templates, each identified by a unique name, stored as text files the owner controls.
- **FR-002**: System MUST let the owner designate one template as the default, applied to every occurrence that does not select another.
- **FR-003**: System MUST let the owner select a named template per calendar event. A selection on a recurring event applies to every instance of the series.
- **FR-004**: Templates MUST support placeholders for at least the following values:
  - the stream title
  - the calendar event's notes, converted to plain text with any per-event settings removed
  - the start date and time and the end time, in the event's time zone, with a configurable format. The format MUST support a day with an ordinal suffix, such as `October 4th, 2026`, `September 1st`, `November 22nd`, and `May 3rd`, as used in the church's existing titles. See [003 reference](../003-lectionary-service-metadata/reference/sunday-examples.md).
  - the time zone name
  - the visibility
  - the stream's duration
  - the occurrence's sequence number within its recurring series
  - owner-defined custom values set globally in configuration or per event in the calendar
- **FR-005**: Templates MUST support simple logic: show a section only when a value is present, and repeat a section over a list of values.
- **FR-006**: Templates MUST support light text formatting (headings, paragraphs, bullet and numbered lists, links, emphasis). The published description MUST be converted to clean, readable plain text, because the platform does not render formatting.
- **FR-007**: Templates MUST be able to include shared snippets, such as a common footer, so the owner can maintain boilerplate in one place.
- **FR-008**: System MUST treat any template error (syntax error, unknown placeholder, missing template, missing included snippet) as a failure for the affected occurrences. It MUST NOT publish partial, blank, or raw template text.
- **FR-009**: System MUST enforce the platform's description limits after rendering: shorten at a clean boundary when too long and remove forbidden characters. Each adjustment MUST be reported as a warning.
- **FR-010**: System MUST let the owner preview the rendered description of any upcoming occurrence without publishing anything.
- **FR-011**: System MUST validate all templates on demand and at the start of every run, and report each problem with the template name, line, and a plain-language explanation.
- **FR-012**: When a template, an included snippet, or a custom value changes, System MUST update every upcoming livestream it manages whose rendered description changed. Unchanged livestreams MUST NOT be touched.
- **FR-013**: System MUST continue to respect manual edits made on the platform. A template change MUST NOT overwrite a livestream the owner edited by hand.
- **FR-014**: When no template is configured, System MUST behave exactly as before this feature: the description is the calendar event's notes.
- **FR-015**: Templates MUST NOT be able to read files outside the templates folder, access the network, run programs, or read credentials or other secrets.
- **FR-016**: Rendering the same template with the same values MUST always produce the same text, so repeated runs never cause needless updates.

### Key Entities

- **Description Template**: A named, owner-authored text document with placeholders, simple logic, and light formatting. Attributes are its name, its content, whether it is the default, and the snippets it includes.
- **Snippet**: A reusable template fragment, such as a footer or a links block, included by one or more templates.
- **Template Values**: The set of values available to a template for one occurrence. It combines event details, time values, sequence number, global custom values, and per-event custom values.
- **Rendered Description**: The final plain-text description produced for one occurrence. It records which template produced it and any warnings from the length and character limits. It is what gets published, and it is compared against the previous one to decide whether to update.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The owner can change boilerplate shared by all upcoming livestreams by editing a single file. Every affected upcoming livestream reflects the change within one scheduler run.
- **SC-002**: 100% of published descriptions contain no unreplaced placeholders, raw template syntax, or raw formatting symbols.
- **SC-003**: 0 livestreams are published or updated with output from a template that has an error.
- **SC-004**: The owner can preview the final description for any upcoming occurrence in under 30 seconds, without any change on the channel.
- **SC-005**: Repeated runs with no template, snippet, value, or calendar changes cause 0 description updates.
- **SC-006**: A new owner can write a working template, including title, local start time, and event notes, in under 10 minutes using the documentation and an example template.

## Assumptions

- Template syntax follows a widely used general-purpose templating language (Jinja-style placeholders and logic, as the owner suggested), and formatting follows Markdown conventions. The owner already knows these, or examples will teach them quickly.
- Descriptions are the focus of this feature. **Title templating** was added by [003 FR-004](../003-lectionary-service-metadata/spec.md) and is available to all events, with optional fallback lists for long titles (004 research S3). Without a title template, the title is the calendar event's title.
- Templates and snippets live in a folder alongside the application's configuration, under the owner's control and version control. They are not edited in a user interface.
- The per-event template choice and per-event custom values are written in the calendar event using the same per-event settings mechanism feature 001 already uses for visibility.
- The sequence number within a series counts the series' instances from its first instance, and it ignores instances removed from the calendar.
- Because the platform shows descriptions as plain text, links are published as full web addresses, and headings become plain lines of text.
- This feature depends on feature 001's mechanisms for updating livestreams, respecting manual edits, retrying under daily usage limits, recording runs, and notifying the owner.
