-- Demo data for fixtures A (original) and B (mirror), then C (room change). See fixtures/fixtures.json.

-- Event E from fixture A, revision 1
INSERT INTO workspace.club_alerts.event_records VALUES
 ('evt-intro-git-1112', 1, 'demo-campus-coding-club', 'intro to git', DATE'2026-11-12', '17:00',
  'Demo Hall 101', 'example.org/rsvp/demo-intro-to-git', 'free', 'published', current_timestamp());

-- Incoming source versions
INSERT INTO workspace.club_alerts.source_announcements VALUES
 ('ann-A', 'src-direct-form', 'https://example.org/flyer/intro-to-git',  current_timestamp(), 'demo-campus-coding-club', 'intro to git', DATE'2026-11-12', '17:00', 'Demo Hall 101', 'example.org/rsvp/demo-intro-to-git', '{}', NULL, NULL),
 ('ann-B', 'src-demo-feed',   'https://example.org/feed/intro-to-git',   current_timestamp(), 'demo-campus-coding-club', 'intro to git', DATE'2026-11-12', '17:00', 'Demo Hall 101', 'example.org/rsvp/demo-intro-to-git', '{}', NULL, NULL),
 ('ann-C', 'src-direct-form', 'https://example.org/flyer/intro-to-git',  current_timestamp(), 'demo-campus-coding-club', 'intro to git', DATE'2026-11-12', '17:00', 'Demo Hall 204', 'example.org/rsvp/demo-intro-to-git', '{}', NULL, NULL),
 ('ann-D', 'src-direct-form', 'https://example.org/flyer/intro-to-git-wk2', current_timestamp(), 'demo-campus-coding-club', 'intro to git', DATE'2026-11-19', '17:00', 'Demo Hall 101', 'example.org/signup', '{}', NULL, NULL);

-- Reconciliation: latest snapshot per event, then rank candidates for each incoming announcement.
-- score 3 = event-specific RSVP match, 2 = exact title + date, 0 = no match.
-- Generic sign-up URLs are excluded from RSVP matching so weekly events stay separate.
CREATE OR REPLACE VIEW workspace.club_alerts.v_reconcile AS
WITH latest AS (
  SELECT * EXCEPT (rn) FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY revision DESC) AS rn
    FROM workspace.club_alerts.event_records
  ) WHERE rn = 1
),
scored AS (
  SELECT
    a.announcement_id,
    e.event_id,
    e.revision,
    CASE
      WHEN a.organizer = e.organizer AND a.rsvp_key = e.rsvp_key
           AND a.rsvp_key NOT LIKE '%/signup%' AND a.local_date = e.local_date THEN 3
      WHEN a.organizer = e.organizer AND a.title_norm = e.title_norm
           AND a.local_date = e.local_date THEN 2
      ELSE 0
    END AS score,
    (a.venue         <=> e.venue)        AS same_venue,
    (a.local_start   <=> e.local_start)  AS same_start,
    (a.local_date    <=> e.local_date)   AS same_date,
    a.venue AS new_venue, e.venue AS old_venue
  FROM workspace.club_alerts.source_announcements a
  JOIN latest e ON a.organizer = e.organizer
)
SELECT
  announcement_id, event_id, revision AS expected_revision, score,
  CASE
    WHEN score = 0 THEN 'new'
    WHEN same_venue AND same_start AND same_date THEN 'linked'
    ELSE 'conflict'
  END AS outcome,
  CASE WHEN NOT same_venue THEN CONCAT(old_venue, ' -> ', new_venue) END AS venue_change
FROM scored
WHERE score > 0
ORDER BY announcement_id, score DESC;

-- Expected: ann-A and ann-B -> linked to evt-intro-git-1112; ann-C -> conflict with 'Demo Hall 101 -> Demo Hall 204';
-- ann-D -> not listed (different date, generic sign-up URL), so the app creates a separate event.
SELECT * FROM workspace.club_alerts.v_reconcile;

-- After the organizer confirms C, write revision 2 and the history becomes visible:
-- INSERT INTO workspace.club_alerts.event_records VALUES
--  ('evt-intro-git-1112', 2, 'demo-campus-coding-club', 'intro to git', DATE'2026-11-12', '17:00',
--   'Demo Hall 204', 'example.org/rsvp/demo-intro-to-git', 'free', 'published', current_timestamp());
