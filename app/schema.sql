PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS clubs (
  club_id      TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  aliases      TEXT NOT NULL DEFAULT '[]',   -- JSON array of known alias strings
  links        TEXT NOT NULL DEFAULT '[]'    -- JSON array of official URLs
);

CREATE TABLE IF NOT EXISTS sources (
  source_id         TEXT PRIMARY KEY,
  club_id           TEXT REFERENCES clubs(club_id),
  kind              TEXT NOT NULL,            -- direct_form | ams_calendar | maritime_feed | demo_feed
  url               TEXT,                     -- allowlisted URL
  enabled           INTEGER NOT NULL DEFAULT 1,
  last_success_at   TEXT
);

CREATE TABLE IF NOT EXISTS events (
  event_id         TEXT PRIMARY KEY,
  club_id          TEXT NOT NULL REFERENCES clubs(club_id),
  current_revision INTEGER NOT NULL DEFAULT 1,
  state            TEXT NOT NULL DEFAULT 'published',  -- draft | published | cancelled
  title            TEXT NOT NULL,
  local_date       TEXT,                      -- YYYY-MM-DD, America/Vancouver
  local_start      TEXT,                      -- HH:MM, NULL = Time TBD
  local_end        TEXT,
  start_utc        TEXT,
  venue            TEXT,
  cost_status      TEXT NOT NULL DEFAULT 'unknown' CHECK (cost_status IN ('free','paid','unknown')),
  beginner_friendly INTEGER,                  -- 1 / 0 / NULL (unknown)
  topics           TEXT NOT NULL DEFAULT '[]',
  rsvp_url         TEXT,
  provenance       TEXT NOT NULL DEFAULT '{}' -- JSON: field -> source_id + evidence
);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(local_date, local_start);

CREATE TABLE IF NOT EXISTS source_announcements (
  announcement_id  TEXT PRIMARY KEY,
  source_id        TEXT NOT NULL REFERENCES sources(source_id),
  external_id      TEXT NOT NULL,
  source_url       TEXT,
  content_hash     TEXT NOT NULL,
  caption          TEXT,
  asset_ref        TEXT,
  detected_at      TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'pending',  -- pending | extracted | review | linked | failed
  candidate        TEXT,                      -- JSON validated fields
  evidence         TEXT,                      -- JSON field -> excerpt
  error            TEXT,
  event_id         TEXT REFERENCES events(event_id),
  UNIQUE (source_id, external_id, content_hash)
);

CREATE TABLE IF NOT EXISTS event_revisions (
  event_id    TEXT NOT NULL REFERENCES events(event_id),
  revision    INTEGER NOT NULL,
  snapshot    TEXT NOT NULL,                  -- JSON of public fields
  changed     TEXT NOT NULL DEFAULT '{}',     -- JSON field -> {old, new}
  reason      TEXT,
  approver    TEXT,
  created_at  TEXT NOT NULL,
  PRIMARY KEY (event_id, revision)
);

CREATE TABLE IF NOT EXISTS review_items (
  review_id         TEXT PRIMARY KEY,
  announcement_id   TEXT NOT NULL REFERENCES source_announcements(announcement_id),
  candidate_ids     TEXT NOT NULL DEFAULT '[]',
  expected_revision INTEGER,
  field_diff        TEXT NOT NULL DEFAULT '{}',
  state             TEXT NOT NULL DEFAULT 'open',  -- open | linked | separate | confirmed | rejected
  reviewer          TEXT,
  created_at        TEXT NOT NULL,
  resolved_at       TEXT
);

CREATE TABLE IF NOT EXISTS subscriptions (
  subscriber_id TEXT PRIMARY KEY,
  email         TEXT NOT NULL UNIQUE,
  topics        TEXT NOT NULL DEFAULT '[]',
  want_free     INTEGER NOT NULL DEFAULT 0,
  want_beginner INTEGER NOT NULL DEFAULT 0,
  after_4pm     INTEGER NOT NULL DEFAULT 0,
  verified_at   TEXT,
  opted_out_at  TEXT,
  verify_token_hash TEXT,
  manage_token_hash TEXT
);

CREATE TABLE IF NOT EXISTS event_outbox (
  event_id    TEXT NOT NULL REFERENCES events(event_id),
  revision    INTEGER NOT NULL,
  kind        TEXT NOT NULL CHECK (kind IN ('new_event','correction')),
  status      TEXT NOT NULL DEFAULT 'pending',   -- pending | complete
  attempts    INTEGER NOT NULL DEFAULT 0,
  retry_at    TEXT,
  PRIMARY KEY (event_id, revision, kind)
);

-- Durable export queue to Databricks Bronze. Rows are written in the SAME transaction as the local
-- change they describe; scripts/dbx_worker.py sends them later, outside any request or transaction.
CREATE TABLE IF NOT EXISTS dbx_queue (
  op_key        TEXT PRIMARY KEY,                -- announcement:<id>:<version> | revision:<event_id>:<revision>
  kind          TEXT NOT NULL CHECK (kind IN ('announcement','revision')),
  aggregate     TEXT NOT NULL,                   -- announcement_id or event_id
  version       INTEGER NOT NULL,                -- projection_version or revision
  payload       TEXT NOT NULL,                   -- JSON parameters for the MERGE
  state         TEXT NOT NULL DEFAULT 'pending', -- pending | claimed | done | failed
  attempts      INTEGER NOT NULL DEFAULT 0,
  claim_expires TEXT,
  next_retry_at TEXT,
  statement_id  TEXT,                            -- in-flight Databricks statement to reconcile after a timeout
  last_error    TEXT,
  created_at    TEXT NOT NULL,
  done_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_dbx_queue_state ON dbx_queue(state, next_retry_at);

CREATE TABLE IF NOT EXISTS deliveries (
  delivery_id    TEXT PRIMARY KEY,
  subscriber_id  TEXT NOT NULL REFERENCES subscriptions(subscriber_id),
  event_id       TEXT NOT NULL REFERENCES events(event_id),
  revision       INTEGER NOT NULL,
  kind           TEXT NOT NULL,
  payload        TEXT,
  state          TEXT NOT NULL DEFAULT 'pending',  -- pending | claimed | accepted | failed | skipped
  claim_token    TEXT,
  claim_expires  TEXT,
  provider_msg_id TEXT,
  UNIQUE (subscriber_id, event_id, revision, kind)
);
