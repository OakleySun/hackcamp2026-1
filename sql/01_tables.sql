-- Databricks Delta tables for UBC Club Alerts.
-- Run in the SQL editor against your team schema. Replace workspace.club_alerts if you use another.
CREATE SCHEMA IF NOT EXISTS workspace.club_alerts;

CREATE TABLE IF NOT EXISTS workspace.club_alerts.source_announcements (
  announcement_id   STRING NOT NULL,
  source_id         STRING,
  source_url        STRING,
  detected_at       TIMESTAMP,
  organizer         STRING,
  title_norm        STRING,
  local_date        DATE,
  local_start       STRING,
  venue             STRING,
  rsvp_key          STRING,
  fields_json       STRING,
  event_id          STRING,
  match_outcome     STRING   -- new | linked | conflict | review
) USING DELTA;

CREATE TABLE IF NOT EXISTS workspace.club_alerts.event_records (
  event_id          STRING NOT NULL,
  revision          INT NOT NULL,
  organizer         STRING,
  title_norm        STRING,
  local_date        DATE,
  local_start       STRING,
  venue             STRING,
  rsvp_key          STRING,
  cost_status       STRING,
  state             STRING,
  published_at      TIMESTAMP
) USING DELTA;
