# Feature Specification: YouTube Livestream Scheduler

**Feature Branch**: `001-youtube-livestream-scheduler`

**Created**: 2026-10-08

**Status**: Draft

**Input**: User description: "build an application that will automatically schedule livestream events on a specific youtube channel"

## Clarifications

### Session 2026-10-08

- Q: How does the owner define what to schedule (FR-016)? → A: Import from an external calendar. The owner maintains events in a calendar, and the application reads its feed.
- Q: How is the application operated? → A: Command-line tool run on a recurring timer, configured with a file. The timer is a **systemd timer, not cron**, decided during planning on 2026-10-08.
- Q: Which channel is the target? → A: The Minnehaha UMC channel, handle **@minnehahaumc** (https://www.youtube.com/@minnehahaumc), channel ID `UCzwZQ34D3RZEncTf6fAe0hQ`.
- Q: How are configuration and secrets kept portable? → A: The church's configuration and templates live in their own version-controlled repository, separate from the application and containing no secrets. Secrets stay on the server as protected credentials. Backups exclude secrets by default and can include them only in a passphrase-encrypted archive. (Decided 2026-10-08 during planning review.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Connect a channel and auto-schedule upcoming livestreams (Priority: P1)

The channel owner connects the application to their YouTube channel once and defines when livestreams should happen. From then on, the application automatically creates the upcoming livestream events on that channel so the owner never has to create them by hand in YouTube.

**Why this priority**: This is the core value of the product. Without automatic creation of scheduled livestream events on the target channel, nothing else matters.

**Independent Test**: Connect a channel, define one livestream schedule, run the application, and confirm the expected upcoming livestream events appear on the channel's scheduled-live list with the correct title, date, and time.

**Acceptance Scenarios**:

1. **Given** the owner has authorized access to their channel and defined a schedule, **When** the scheduler runs, **Then** every livestream that falls within the scheduling horizon exists on the channel as an upcoming event with the correct title, description, start time, and visibility.
2. **Given** the owner has not yet authorized access to a channel, **When** the scheduler attempts to run, **Then** no events are created and the owner is told that channel access is required.
3. **Given** the owner signs in with an account or brand account that is not @minnehahaumc, **When** they connect, **Then** the connection is refused, naming both the expected channel and the one that was authorized, and they can retry choosing the correct channel.

---

### User Story 2 - Keep the schedule in sync without duplicates (Priority: P2)

The application runs repeatedly and unattended. Each run must add newly due events and leave already-created ones alone, and it must reflect schedule changes made by the owner.

**Why this priority**: Automation is only trustworthy if repeated runs are safe. Duplicate or stale events on a public channel are visible to the audience.

**Independent Test**: Run the scheduler twice in a row with no changes and confirm no new events appear on the second run. Then change a schedule and confirm the affected upcoming events are updated or removed accordingly.

**Acceptance Scenarios**:

1. **Given** events for the next several weeks already exist on the channel, **When** the scheduler runs again with no schedule changes, **Then** no duplicate events are created.
2. **Given** the owner changes the start time or title in a schedule, **When** the scheduler next runs, **Then** upcoming events created by this application are updated to match.
3. **Given** the owner removes a schedule or cancels a specific occurrence, **When** the scheduler next runs, **Then** the corresponding upcoming events created by this application are removed from the channel.
4. **Given** an event on the channel was created manually (not by this application), **When** the scheduler runs, **Then** that event is never modified or deleted.
5. **Given** a livestream created by hand already exists within 15 minutes of an occurrence's start, **When** the scheduler runs, **Then** no new livestream is created for that occurrence, the existing one is unchanged, and the owner is notified once.

---

### User Story 3 - See what was scheduled and what failed (Priority: P3)

The owner can review what the application has scheduled, when it last ran, and any problems, so they trust it and can act when something goes wrong.

**Why this priority**: Unattended automation needs visibility, but the scheduling itself delivers value first.

**Independent Test**: Run the scheduler with one valid schedule and one that will fail, then confirm the owner can see the successful events, the failure, and the reason.

**Acceptance Scenarios**:

1. **Given** the scheduler has run, **When** the owner opens the activity view, **Then** they see each run's time, the events created, updated, or removed, and any errors.
2. **Given** a run fails (for example, access has expired or the platform's daily limit was reached), **When** the owner checks, **Then** the failure and a plain-language reason are shown, and the owner is notified.

---

### User Story 4 - Back up, restore, and move the installation (Priority: P3)

The owner keeps the church's settings and templates in their own versioned repository, separate from the application, so changes are tracked and can be reapplied anywhere. The application's own records, such as which livestreams it created, are backed up automatically. When the home server is replaced or rebuilt, the owner restores onto the new machine, and the application carries on managing the same livestreams. It does not orphan them, and it does not duplicate them.

**Why this priority**: Nothing is lost day to day without it, but a failed disk or a new server would otherwise leave the application unable to manage livestreams it created. It would see them as created by hand, never touch them again, and never replace them.

**Independent Test**: Run the scheduler and let it create livestreams. Take a backup, build a fresh server from the configuration repository plus the backup, and run the scheduler there. Existing livestreams are still recognized as the application's own (updates apply, nothing is duplicated), and no secret appears in the default backup.

**Acceptance Scenarios**:

1. **Given** the configuration repository and a backup, **When** the owner installs on a fresh server and restores, **Then** the next run updates and removes the application's existing livestreams exactly as before, with 0 duplicates and 0 orphaned livestreams.
2. **Given** a default backup, **When** its contents are inspected, **Then** it contains no secrets (no channel login token, calendar address, mail password or API client secret). The owner supplies those again on the new server, or restores them from an encrypted backup.
3. **Given** a backup taken with secrets included, **When** it is restored with the correct passphrase, **Then** the new server needs no re-authorization. **When** the passphrase is wrong, **Then** nothing is restored.
4. **Given** the owner commits a template change to the configuration repository, **When** the server's configuration is updated from the repository, **Then** the change is validated before use. An invalid change is rejected and the previous configuration stays active.
5. **Given** automatic backups are enabled, **When** a day passes, **Then** a new backup exists and backups older than the retention period are removed.

---

### Edge Cases

- **Application records lost without a backup**: the application treats its own existing livestreams as created by hand. It never touches or duplicates them (safe), and the owner is told how many upcoming livestreams are no longer managed. Restoring a backup returns them to management.
- **Restoring an older backup**: livestreams created after that backup are treated as created by hand (safe, never duplicated, owner told once). Everything recorded in the backup is managed normally.
- Channel access expires or is revoked between runs: the run stops, nothing is partially corrupted, and the owner is notified to reconnect.
- The platform rejects event creation because a daily usage limit is reached: remaining events are retried on a later run, and the owner can see which are pending.
- The channel is not eligible for livestreaming: the owner gets a clear explanation instead of silent failure.
- A scheduled start time falls in the past, or at a daylight-saving transition: past times are skipped; times are interpreted in the owner's configured time zone and remain correct across daylight-saving changes.
- Two schedules would create events at the same time: both are created only if the owner confirms; by default the owner is warned about the overlap.
- A livestream created by hand already exists at the same time as a calendar occurrence (e.g. at cut-over from manual scheduling): no duplicate is created, the existing livestream is never modified, and the owner is told once. If that livestream is later deleted, the application schedules its own (FR-017).
- An event created by this application is edited or deleted manually on the channel: the application detects this and respects the manual change by default rather than recreating it repeatedly.
- The application is down for several days: on restart it catches up and creates any events that are now within the horizon, without duplicating existing ones.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let the owner connect exactly one specific YouTube channel by granting the application permission to manage that channel's livestream events, and MUST show which channel is connected. The target channel is **@minnehahaumc** (Minnehaha UMC). It is configured, not hard-coded. System MUST refuse to complete a connection, and MUST refuse to run, if the authorized account resolves to any other channel.
- **FR-002**: System MUST let the owner disconnect the channel and revoke the application's access at any time.
- **FR-003**: System MUST let the owner define one or more livestream schedules, each with a title, description, start time, expected duration, visibility (public, unlisted, or private), and time zone.
- **FR-004**: System MUST support schedules that repeat (for example weekly on given days) and one-off schedules for a single date.
- **FR-005**: System MUST automatically create upcoming livestream events on the connected channel for every occurrence within a configurable scheduling horizon (default: 4 weeks ahead).
- **FR-006**: System MUST run automatically on a recurring basis without the owner being present.
- **FR-007**: System MUST NOT create duplicate events for an occurrence that already has an event created by this application.
- **FR-008**: System MUST update or remove upcoming events it created when the owner changes or deletes the corresponding schedule or occurrence.
- **FR-009**: System MUST NOT modify or delete any event on the channel that it did not create.
- **FR-010**: System MUST allow the owner to skip or cancel an individual occurrence without deleting the whole schedule.
- **FR-011**: System MUST record each run, including time, events created, updated, removed, skipped, and any errors, and make this viewable to the owner.
- **FR-012**: System MUST notify the owner when a run fails or when channel access needs to be renewed.
- **FR-013**: System MUST retry transient failures and events deferred by platform usage limits on a later run without creating duplicates.
- **FR-014**: System MUST interpret all schedule times in the owner's chosen time zone and handle daylight-saving changes correctly.
- **FR-015**: System MUST protect the owner's channel access credentials so they are never shown in the interface or logs.
- **FR-016**: System MUST read livestream schedules from an external calendar that the owner maintains (a subscribed calendar feed). Each calendar event, including each instance of a recurring event, becomes one occurrence. Deleting an event or instance in the calendar cancels that occurrence, and editing it changes the occurrence. Per-event settings that a calendar cannot express, such as visibility, come from defaults in the application configuration and may be overridden per event.
- **FR-017**: System MUST NOT create a livestream for an occurrence when a livestream not created by the application already exists on the channel within 15 minutes of the occurrence's start. It MUST leave that livestream unmodified, record the occurrence as already present, and notify the owner once. This is the same rule as [004 FR-010](../004-taize-funeral-services/spec.md); it ships with this feature.
- **FR-018**: The church's configuration (settings, templates, service types) MUST be storable in an owner-controlled, version-controlled location separate from the application, and MUST contain no secrets. Updating the server from it MUST validate the new configuration first and keep the previous one active if validation fails.
- **FR-019**: System MUST provide backup and restore of its own records together with the active configuration. Backups MUST exclude secrets by default. Secrets MAY be included only in a passphrase-encrypted backup.
- **FR-020**: System MUST take an automatic backup at least daily and keep a configurable number of them (default 14).
- **FR-021**: After restore on a new server, System MUST continue managing every livestream recorded in the backup. A restore MUST be refused if the backup is from a newer application version than the one installed.
- **FR-022**: All secrets, including the API client secret, MUST be supplied through the same protected-credential mechanism. None of them may live in the configuration repository.

### Key Entities

- **Channel Connection**: The single YouTube channel the application is authorized to manage; has a channel name, authorization status, and expiry state.
- **Schedule**: A rule describing a livestream or series of livestreams; has title, description, start time, duration, visibility, time zone, recurrence pattern (or single date), and active/inactive state.
- **Occurrence**: One specific date and time produced by a schedule; can be pending, scheduled, skipped, cancelled, or failed; links to at most one Livestream Event.
- **Livestream Event**: The upcoming event as it exists on the channel; records that it was created by this application and its current details.
- **Configuration Repository**: The owner's versioned settings, templates and service types for the church. It holds no secrets.
- **Backup**: A point-in-time copy of the application's records and active configuration, with an application version and schema version. Secrets are excluded unless it is encrypted.
- **Run Record**: One execution of the scheduler; has start and end time, counts of events created, updated, removed, and skipped, and any errors.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Once the platform's API access is registered and the home server is prepared (base operating system installed, network up), a single guided install plus the one-time channel authorization takes under 10 minutes. After that, the owner has upcoming livestream events appearing on the channel with no further manual event creation.
- **SC-002**: 100% of occurrences within the scheduling horizon have a matching upcoming event on the channel after a successful run.
- **SC-003**: Repeated runs with no schedule changes produce zero duplicate events across at least 30 consecutive runs.
- **SC-004**: Schedule changes made by the owner are reflected on the channel within one run cycle and no later than 24 hours.
- **SC-005**: Zero manually created channel events are altered or removed by the application.
- **SC-006**: The owner is notified of a failed run or expired access within 1 hour of detection.
- **SC-007**: The owner can find what was scheduled in the last run, and why anything failed, in under 1 minute.
- **SC-008**: Moving to a fresh server (configuration repository plus backup) takes under 20 minutes, after which 100% of previously managed upcoming livestreams are still managed, with 0 duplicates.
- **SC-009**: 0 secrets are found in the configuration repository or in any default backup.

## Assumptions

- The application serves a single owner and a single YouTube channel for this version: @minnehahaumc. Multiple channels and multiple users are out of scope.
- @minnehahaumc is likely a YouTube brand account. The person connecting must be an Owner or Manager of it and must pick that channel on Google's account chooser during sign-in.
- The channel is already enabled for livestreaming on YouTube.
- Creating the event only schedules it. Actually going live (starting the stream with encoder software) remains a separate action by the owner and is out of scope.
- Thumbnails, chat moderation, and analytics are out of scope for the first version.
- The scheduling horizon defaults to 4 weeks and is configurable.
- Owner notifications are delivered by email, which the owner supplies during setup.
- The application runs on the owner's **own Ubuntu server at home**, not on a cloud host. It needs only outbound internet access. No inbound ports or port forwarding are required. Power or network outages are caught up automatically on the next run.
- Using the platform's API requires a one-time, free registration in the platform owner's developer console to obtain API credentials. That registration involves no hosting or billing.
- Manually edited or deleted application-created events are respected by default and not recreated.
