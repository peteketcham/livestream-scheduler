-- 0001_init: 001 data model (specs/001-youtube-livestream-scheduler/data-model.md)
-- All timestamps are UTC ISO-8601 strings: YYYY-MM-DDTHH:MM:SSZ

CREATE TABLE channel_connection (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    channel_id       TEXT NOT NULL,
    channel_title    TEXT NOT NULL,
    channel_handle   TEXT NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('connected', 'needs_reauth', 'not_eligible')),
    status_reason    TEXT,
    connected_at     TEXT NOT NULL,
    last_verified_at TEXT
);

CREATE TABLE calendar_source (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    url_hash         TEXT,          -- SHA-256 of the configured URL; the URL itself is never stored
    etag             TEXT,
    last_modified    TEXT,
    last_fetched_at  TEXT,
    last_body_sha256 TEXT,
    last_event_count INTEGER
);

CREATE TABLE run (
    id              INTEGER PRIMARY KEY,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    trigger         TEXT NOT NULL CHECK (trigger IN ('timer', 'manual')),
    outcome         TEXT CHECK (outcome IN ('success', 'partial', 'failed', 'skipped_locked')),
    dry_run         INTEGER NOT NULL DEFAULT 0,
    created         INTEGER NOT NULL DEFAULT 0,
    updated         INTEGER NOT NULL DEFAULT 0,
    removed         INTEGER NOT NULL DEFAULT 0,
    skipped         INTEGER NOT NULL DEFAULT 0,
    deferred        INTEGER NOT NULL DEFAULT 0,
    failed          INTEGER NOT NULL DEFAULT 0,
    error_class     TEXT CHECK (error_class IN
                        ('auth', 'quota', 'feed', 'not_eligible', 'safety_hold', 'internal')),
    error_message   TEXT,
    quota_units_est INTEGER NOT NULL DEFAULT 0,
    config_commit   TEXT
);

CREATE TABLE occurrence (
    id                    INTEGER PRIMARY KEY,
    key                   TEXT UNIQUE NOT NULL,
    ical_uid              TEXT NOT NULL,
    original_start_utc    TEXT,
    title                 TEXT NOT NULL,
    description           TEXT NOT NULL,
    start_utc             TEXT NOT NULL,
    end_utc               TEXT NOT NULL,
    source_tz             TEXT NOT NULL,
    visibility            TEXT NOT NULL CHECK (visibility IN ('public', 'unlisted', 'private')),
    desired_hash          TEXT NOT NULL,
    state                 TEXT NOT NULL CHECK (state IN (
                              'pending', 'creating', 'scheduled', 'skipped', 'cancelled', 'failed',
                              'conflict', 'owner_modified', 'owner_deleted', 'past',
                              'exists_external')),
    state_reason          TEXT,
    deferred_reason       TEXT CHECK (deferred_reason IN ('quota', 'transient')),
    attempts              INTEGER NOT NULL DEFAULT 0,
    intent_at             TEXT,
    local_override        TEXT CHECK (local_override IN ('skip', 'approve_overlap')),
    first_seen_run_id     INTEGER REFERENCES run(id),
    last_seen_run_id      INTEGER REFERENCES run(id),
    updated_at            TEXT NOT NULL,
    -- 004 S6 / 001 FR-017: a livestream created by hand blocks our create; never modified
    external_broadcast_id TEXT,
    external_title        TEXT,
    external_start_utc    TEXT
);
CREATE INDEX occurrence_state ON occurrence(state);
CREATE INDEX occurrence_start ON occurrence(start_utc);

CREATE TABLE broadcast (
    broadcast_id          TEXT PRIMARY KEY,
    occurrence_id         INTEGER UNIQUE REFERENCES occurrence(id),
    channel_id            TEXT NOT NULL,
    created_at            TEXT NOT NULL,
    last_written_hash     TEXT NOT NULL,
    last_written_at       TEXT NOT NULL,
    last_seen_remote_hash TEXT,
    life_cycle_status     TEXT,
    bound_stream_id       TEXT,
    deleted_at            TEXT
);

CREATE TABLE run_item (
    id            INTEGER PRIMARY KEY,
    run_id        INTEGER NOT NULL REFERENCES run(id) ON DELETE CASCADE,
    occurrence_id INTEGER REFERENCES occurrence(id) ON DELETE SET NULL,
    action        TEXT NOT NULL,   -- open set; see data-model.md
    broadcast_id  TEXT,
    result        TEXT NOT NULL CHECK (result IN ('ok', 'deferred', 'error')),
    message       TEXT
);
CREATE INDEX run_item_run ON run_item(run_id);

CREATE TABLE notification (
    problem_key  TEXT PRIMARY KEY,
    opened_at    TEXT NOT NULL,
    last_sent_at TEXT,
    resolved_at  TEXT,
    summary      TEXT
);
