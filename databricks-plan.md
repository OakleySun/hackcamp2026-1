# Plan: Make Databricks the "campus events intelligence" layer of UBC Club Alerts

## Context

Right now Databricks only appears in two hand-run SQL files (`sql/01_tables.sql`, `sql/02_demo_data_and_reconcile.sql`). The app never calls it, and the plan treats it as optional. That will lose **Best Use of Databricks**, which is judged in person by Jacklyn Biggin on the "most creative and well-thought-out use".

At HackCamp, Databricks ran a workshop ([`databricks-solutions/data-intelligence-for-smarter-community`](https://github.com/databricks-solutions/data-intelligence-for-smarter-community)). It built:

- Bronze → Silver → Gold tables
- an AI/BI dashboard
- a Genie space
- a Databricks App (FastAPI + React + Leaflet) with a UBC campus map built from UBC Geodata (CC BY 4.0) and an "Ask Genie" panel

The mentors also pushed Genie hard. Following that pattern closely, with our own real problem, shows the judge we built on what she taught.

**Decisions**

- Scope: full, about 8–12 hours.
- Genie is student-facing: "Ask Genie" on the site.
- Backend host: undecided. The website is on Vercel.

**Story for the judge:** "Club posts come in messy and duplicated. Databricks cleans them with AI, places every event on the UBC campus map, catches duplicates and room changes, and lets students just ask for what they want."

## Recommendation on hosting (resolves the Vercel/SQLite question)

- Keep the FastAPI backend on **Render or Railway with a persistent disk**. SQLite and all 8 passing tests stay unchanged, and Vercel only hosts the website.
- The **Databricks App** hosts only the campus map and Ask Genie panel.
- Lakebase or Supabase would mean rewriting the database layer for Postgres. Don't do that this weekend.

## Phase 0: Workspace check (30 min, do first)

In the Free Edition workspace, confirm each item and record what's missing:

- [ ] a serverless SQL warehouse (note its ID)
- [ ] `ai_query` / `ai_classify` with a foundation model endpoint (for example a `databricks-meta-llama-*` endpoint)
- [ ] an embeddings endpoint (`databricks-gte-large-en`)
- [ ] Genie
- [ ] Databricks Apps
- [ ] Vector Search
- [ ] creating a catalog or schema and a Volume

Then:

- Create `workspace.club_alerts_bronze`, `_silver` and `_gold`, or one catalog with three schemas, as in the workshop.
- Create a service principal or PAT for the backend, with read on gold, write on bronze, and access to the Genie space.

## Phase 1: Data in (Bronze), about 2 hours

1. **`app/databricks.py` (new):** a small client for the SQL Statement Execution API.
   - It sends parameterized statements and polls them by statement ID, using `httpx`, which is already a dependency.
   - Settings come from `DATABRICKS_HOST`, `DATABRICKS_WAREHOUSE_ID` and `DATABRICKS_TOKEN`.
   - If those aren't set, it does nothing.
2. **`app/schema.sql`:** add a `dbx_queue` table (id, kind, payload JSON, attempts, created_at).
3. **`app/service.py`:** queue a row whenever a source announcement is processed and whenever `create_event` or `update_event` writes a revision.
   - Add `flush_dbx_queue()`, which runs `MERGE` statements keyed on announcement_id and on (event_id, revision).
   - Call it at the end of intake and review resolve, wrapped in try/except so a Databricks failure never breaks the app.
4. **Bronze tables** (`sql/10_bronze.sql`, replacing `01_tables.sql`):
   - `bronze.source_announcements`: raw caption, source, detected_at, Gemini candidate JSON
   - `bronze.event_revisions`: snapshot JSON, changed JSON, reason
   - `bronze.engagement_daily`: anonymous counts per event per action per day, with no profile IDs or emails
5. **Seed dataset** (`databricks/notebooks/01_seed_events.py`): about 80 realistic fictional UBC club events across the 8 topic slugs, real campus buildings, 2 weeks of dates, and some deliberate duplicates and room changes. This gives the dashboard and Genie enough to work with. Label it as demo data.
6. **UBC Geodata** (`databricks/notebooks/00_setup.py`): copy the workshop's building geojson into a Volume and build `silver.buildings` (code, name, aliases, lat, lon). Credit UBC Geodata (CC BY 4.0).

## Phase 2: AI cleaning (Silver and Gold), about 3 hours. This is the creative core.

All SQL lives in `sql/`, and one scheduled Lakeflow Job (`databricks/jobs/pipeline.sql`, every 10 minutes) runs it.

1. **`silver.events`:** parse the candidate JSON.
   - `ai_classify(title || description, ARRAY(<8 topic slugs>))` checks or fills the topics.
   - **Venue to building:** match exact names and aliases first, then `ai_query` with structured output picks a building code from `silver.buildings` for free text like "Nest 2nd floor" or "the big Engineering building". Store the confidence. Low confidence becomes "Location unclear".
2. **`gold.match_candidates`:** pairs of events from the same club within ±1 day, plus pairs whose embeddings are close if Vector Search exists (otherwise `ai_query` embeddings with cosine similarity in SQL).
3. **`gold.match_judgements`:** `ai_query` with a JSON schema returning `{same_event: bool, changed_fields: [...], reason: string}` for each candidate pair. This catches "Intro to Git" vs "Git Workshop for Beginners", which our exact matcher misses. The backend uses it in **Phase 4**.
4. **`gold.events_current`:** latest revision per event, joined to building lat/lon and topics. These are the public fields only.
5. **`gold.event_history`:** every revision. The demo shows the room change through Delta `DESCRIBE HISTORY` / `VERSION AS OF`.
6. **`gold.campus_activity`:** counts by topic, building, weekday and hour.
   - `gold.opportunity_gaps`: topics with few beginner-friendly after-4pm events, as a community-impact insight for the AMS and clubs.

## Phase 3: Genie, dashboard and campus map app, about 3–4 hours

1. **Genie space "Club Events":**
   - tables: `gold.events_current`, `gold.campus_activity`, `silver.buildings`
   - written instructions: the topic slugs, "after 4 p.m." meaning local start ≥ 16:00 Vancouver time, unknown cost not counting as free, only upcoming events, and always return event_id
   - 6 to 8 example questions and SQL in `databricks/genie/instructions.md`
2. **`POST /api/ask` in `app/main.py`:**
   - proxies the Genie Conversation API: start a conversation, poll the message, fetch the query result
   - returns Genie's text answer plus the matching event IDs, which the website renders as normal cards
   - holds the token server-side, rate-limits per IP, and doesn't store questions
   - Genie can only see public gold tables, never subscribers
   - returns `503` with a friendly message when it isn't configured
3. **AI/BI dashboard "Campus Club Pulse":**
   - events this week by topic and building
   - % beginner-friendly
   - duplicates caught by the AI judge
   - corrections sent
   - opportunity gaps
4. **Databricks App "Campus Events Map"** (`databricks/app/`):
   - adapted from the workshop's `reference_code/app` (FastAPI + React + Leaflet); check its LICENSE first
   - pins events from `gold.events_current` on UBC buildings, with time and topic filters and an Ask Genie panel
   - the Vercel site links to it with "View on campus map"

## Phase 4: Backend uses Databricks for matching (Step 7 of `ubc-club-alerts.md`), about 1 hour

- In `service.process`, when a new candidate has no exact match, query `gold.match_judgements` (or call `ai_query` directly through the Statement API) for a same-event verdict with a 5-second timeout.
  - `same_event = true` goes to the review queue with the AI's reason shown to the reviewer. It never links automatically.
  - On timeout or error, log it and continue with local `matching.decide`.

## Maritime handoff (a teammate owns the agent)

- No Maritime work in this plan beyond readiness:
  - `POST /api/intake` (existing) is the agent's target
  - the agent gets its own `SOURCE_INGEST_TOKEN`
  - its posts carry `source_id` `src-maritime-feed`, added to the fixtures and seed
- Bronze keeps `source_id` and `detected_at`, so the dashboard can show "found by Maritime agent" vs "submitted by club". That links the two prizes in the demo.
- The backend must be deployed with a public HTTPS URL (Render or Railway) before the teammate can schedule the agent. Do this right after Phase 1.

## Files

- **New:**
  - `app/databricks.py`
  - `sql/10_bronze.sql`, `20_silver.sql`, `30_gold.sql`, `40_match_judge.sql`
  - `databricks/notebooks/00_setup.py`, `01_seed_events.py`
  - `databricks/jobs/pipeline.sql`
  - `databricks/genie/instructions.md`
  - `databricks/app/` (app.yaml, backend, frontend)
  - `tests/test_databricks.py`
- **Edit:**
  - `app/schema.sql` (dbx_queue)
  - `app/service.py` (queue, flush, AI match hook)
  - `app/main.py` (`/api/ask`)
  - `.env.example` (`DATABRICKS_TOKEN`, `GENIE_SPACE_ID`, `DATABRICKS_TIMEOUT_S`)
- **Delete:** `sql/01_tables.sql` and `sql/02_demo_data_and_reconcile.sql`, which the new files replace.
- **Reuse:** `service.snapshot`, `service.get_event`, `service.public_event`, `matching.decide`, `db.load_fixtures`, and the workshop's map app and geojson.

## Verification

- **`pytest`:** existing 8 tests plus new tests that use a fake Databricks client:
  - while offline, the queue fills and the app still works
  - the flush sends `MERGE`s and clears the queue
  - an AI "same event" verdict creates a review item and doesn't link automatically
  - a timeout falls back to local matching
  - `/api/ask` returns 503 when not configured, and maps Genie rows to event cards when it is
- **In the Databricks workspace:**
  - run the setup and seed notebooks and the pipeline job
  - check that `gold.match_judgements` flags the seeded near-duplicates
  - check that venue→building resolves the fuzzy venues
  - ask Genie "free beginner tech events after 4 this week near the Nest" and get correct rows
  - check that the dashboard renders and that the App map shows pins
- **End to end:**
  - run the backend locally with a real `.env`
  - submit fixtures A–C and see them appear in bronze, then gold after the job runs
  - check that `/api/ask` answers from the site
- **Judge demo (60 seconds):**
  1. a messy flyer comes in
  2. it appears on the campus map
  3. a near-duplicate is caught by the AI judge with a reason
  4. the room change shows in Delta history
  5. a student asks Genie in plain English
  6. the dashboard shows an opportunity gap

## Risks and fallbacks

- If Vector Search isn't on Free Edition, use embeddings through `ai_query` and cosine similarity in SQL.
- If Apps aren't available, show the map inside the AI/BI dashboard (map widget) and keep Ask Genie on the Vercel site.
- If `ai_query` quota runs out, cache the judgements in gold so each pair is judged only once.
- If the Genie API is slow, show a "thinking" state, and keep the normal filters as the main path.
