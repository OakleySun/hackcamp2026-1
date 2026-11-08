# Quad — UBC club events

Quad collects events from across UBC Vancouver so students can find something to do, see where it is, and check the original listing. Start with [Explore on Quad](https://4774d003-8629-4264-90d6-274ad60172ce.mtm.sh/explore) or run the demo locally.

## What's in this repo

| Area | What it does |
| --- | --- |
| [`frontend/`](frontend/) | React/TanStack Start website: Discover, Explore, a campus map, event pages, saved events, accounts, and topic preferences. |
| [`app/`](app/) | FastAPI and SQLite: intake, event matching, publication, revision history, reviews, and subscription/delivery APIs. SQLite is the source for the live site. |
| [`scripts/`](scripts/) and [`config/`](config/) | Maritime monitors AMS and UBC calendars, club sites from the AMS directory, and a rotating Instagram watchlist using a private browser session. See the [source list](source-coverage.md) and [directory coverage](club-monitoring.md). |
| [`maritime/`](maritime/) and [`Dockerfile`](Dockerfile) | Host the website and API together with persistent SQLite. Separate scheduled workers check sources and try to complete missing information. |
| [`databricks/`](databricks/) | The exporter sends announcements and event revisions to Bronze in the background. The notebooks and Genie instructions are the starting point for analytics and questions about published events. |

The pipeline is **source → intake → match/review → publish → export**. Structured listings use their own fields. Gemini can extract fields from unstructured captions and uploaded flyers. The enrichment worker checks incomplete UBC Events items against official pages and automatically publishes or links confirmed matches; conflicting or unverified items stay in review. Event topics use the same eight labels in the API, website filters, and Databricks. Quad keeps existing tags and fills missing ones from clear listing text. A background Gemini pass classifies upcoming events still missing tags and skips listings with too little evidence. A tag update does not resend an alert.

## Run locally

Use Python 3.11+ and Bun (or Node.js with `npx`). On Windows, from the repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env  # First setup only; keep an existing .env.
.\.venv\Scripts\python.exe -m scripts.run_demo all
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

On macOS/Linux, use `python3` to create the environment, `.venv/bin/python` to run it, and `cp .env.example .env` for first setup. The fixture demo needs no cloud keys: keep `APP_MODE=demo` and leave `GEMINI_API_KEY` blank. For a demo alongside another setup, point `DATABASE_PATH` to a separate file such as `data/quad-demo.db`.

In a second terminal:

```sh
cd frontend
bun install --frozen-lockfile
bun run dev
```

Use `npx bun install --frozen-lockfile` and `npm run dev` if Bun isn't on your PATH. Open [localhost:8080](http://localhost:8080) and check the [API health endpoint](http://127.0.0.1:8000/health). The website defaults to the local API on port 8000; use `frontend/.env.local` to set `VITE_API_URL` if needed. Demo fixtures use fixed dates, so you can inspect them after those dates at [/api/events?include_past=true](http://127.0.0.1:8000/api/events?include_past=true).

Run `python -m pytest -q` from the root with the virtual environment active and `bun run test` from `frontend/` before pushing. Use the [Maritime notes](maritime-setup.md) for source configuration and the [Instagram notes](instagram-browser-setup.md) for browser access. Keep credentials in local `.env` files or the relevant service's secret settings.

## Demo: announce an event, then change its room

Show Explore alongside a terminal. The audience will see **Intro to Git** appear in **Demo Hall 101**, see the test alert you send with its link, and then watch that same event page update to **Demo Hall 204**.

1. **Start with an empty demo feed.** Follow the frontend setup above and point it at `http://127.0.0.1:8000`. For the backend, run the commands below from the repo root with port 8000 free. They use a fresh local database. Skip `scripts.run_demo all` so the event stays unpublished until step 3. The sample event is dated Nov. 12, 2026. For a later rehearsal, set `local_date` in candidates A and C in [`fixtures/fixtures.json`](fixtures/fixtures.json) to the same upcoming date and change the dates in their captions to match.

   ```powershell
   $env:DATABASE_PATH = "data/quad-demo-$([guid]::NewGuid().ToString('N')).db"
   $env:APP_MODE = 'demo'
   $env:SOURCE_INGEST_TOKEN = 'quad-local-demo'
   $env:REVIEWER_TOKEN = 'quad-local-demo'
   .\.venv\Scripts\python.exe -c "import os; os.environ['GEMINI_API_KEY'] = ''; import uvicorn; uvicorn.run('app.main:app', port=8000)"
   ```

2. **Open [Explore](http://localhost:8080/explore) and confirm it’s empty.** Run this in the browser’s developer console, then close the console. It makes this demo tab check for changes every two seconds as you click from Explore to the event page. If you reload the tab, run it again. A manual refresh also works as a fallback.

   ```js
   clearInterval(window.quadDemoRefresh);
   window.quadDemoRefresh = setInterval(() => window.__TSR_ROUTER__?.invalidate(), 2000);
   ```

3. **Publish and send the test alert.** In a second PowerShell terminal at the repo root, submit fixture A as the organizer announcement. Watch the card appear and open it. Manually send a message to your demo inbox with the event link printed below. Suggested copy: “New event: Intro to Git, 5 p.m. in Demo Hall 101. View on Quad.” Open the link on the presenter’s machine, where Quad is running.

   ```powershell
   $api = 'http://127.0.0.1:8000'
   $headers = @{ Authorization = 'Bearer quad-local-demo' }
   $fixtures = Get-Content fixtures/fixtures.json -Raw -Encoding UTF8 | ConvertFrom-Json
   $first = Invoke-RestMethod "$api/api/intake" -Method Post -Headers $headers `
     -ContentType 'application/json; charset=utf-8' -Body ($fixtures.announcements.A | ConvertTo-Json)
   "http://localhost:8080/events/$($first.event_id)"
   ```

4. **Announce a room change while the event page stays open.** Submit fixture C in the same terminal. Quad recognizes the original listing and opens a review. Point out that the public page still says **Demo Hall 101** until you confirm the change.

   ```powershell
   $change = Invoke-RestMethod "$api/api/intake" -Method Post -Headers $headers `
     -ContentType 'application/json; charset=utf-8' -Body ($fixtures.announcements.C | ConvertTo-Json)
   $change | Select-Object state, review_id, reason
   ```

5. **Confirm and show the update.** Watch **Where** change to **Demo Hall 204** and scroll to **Confirmed changes** to show the old and new rooms. The event keeps the same URL, so the original alert still takes people to the current details. Return to Explore to show one event card with the **Updated** badge.

   ```powershell
   $current = Invoke-RestMethod "$api/api/events/$($first.event_id)"
   $decision = @{ decision = 'confirm'; expected_revision = $current.current_revision; reviewer = 'demo' }
   Invoke-RestMethod "$api/api/reviews/$($change.review_id)/resolve" -Method Post -Headers $headers `
     -ContentType 'application/json' -Body ($decision | ConvertTo-Json)
   ```

**Presenter line:** “We announced the workshop, then corrected the room. Students can use the link they already have and see what changed.”

For the scheduled n8n demo, use the [campus notification workflow](n8n/README.md). It can preview a Vancouver morning digest and a one-hour reminder, then deliver a sample through Gmail or ntfy after those channels are connected.

## Campus Pulse

[Campus Pulse](https://hackcamp2026-1.vercel.app/pulse) shows Databricks analysis of the real Quad event feed. Quad exports announcements and event revisions to Bronze. The Quad Pulse job runs the [Silver and Gold pipeline](databricks/notebooks/02_pipeline.sql) when either Bronze table changes, with at least ten minutes between runs. The [final notebook step](databricks/notebooks/03_publish_pulse.py) returns the metrics and up to 12 recently analyzed events. Quad checks for a completed run every five minutes, caches the last successful snapshot, and verifies that each displayed event still matches a published revision and linked source.

Set `DATABRICKS_PULSE_JOB_ID` on the backend to the ID of the Databricks job. Its notebook task key is `pipeline`. The existing Databricks credentials also authorize the result check.

## What to add next

These are the open items from the [original build plan](ubc-club-alerts.md) and the [Databricks plan](databricks-plan.md).

1. **Genie: try a new club.** Ask, “Give me three free events this week from three different organizers.” Genie should return a varied shortlist from Quad's existing listings, with the organizer, date/time, and source link for each. Use Vancouver time, confirmed free admission, and one result per organizer ID. If fewer than three qualify, show the available matches. Test it in the [Genie space](databricks/genie/instructions.md) before adding any chat UI to Quad.
2. **Alerts: finish the test inbox loop.** The backend has subscription and delivery endpoints. The plan still calls for an n8n workflow export and an end-to-end check: one event alert on replay, one room correction to original recipients, and no message after unsubscribe. Start with a test inbox.
3. **Organizer intake: expose the existing API in the website.** Add a small flyer or caption submission flow with a preview and a way to confirm missing details. Keep intake credentials server-side. The current review inbox is for operators.
4. **Later: duplicate evidence and coverage.** Wire asynchronous Databricks match suggestions into the existing review flow and test recurring events and late results before relying on the model. Add a small dashboard for source coverage and missing fields. A public Genie endpoint can wait until its data access and fallback have been tested.

For a four-person team: one person can own the website and demo, one can own source checks and enrichment, one can own backend and alert verification, and one can own the Databricks view and Genie. Rehearse together with one real listing: find it in Quad, open its source, then find it again with Genie.
