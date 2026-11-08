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

The pipeline is **source → intake → match/review → publish → export**. Structured listings use their own fields. Gemini can extract fields from unstructured captions and uploaded flyers. The enrichment worker checks incomplete UBC Events items against official pages and automatically publishes or links confirmed matches; conflicting or unverified items stay in review. Event topics use the same eight labels in the API, website filters, and Databricks. Existing tags are kept; missing tags are filled from clear listing text, including for older events when the API starts. A tag update does not resend an alert.

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

## What to add next

These are the open items from the [original build plan](ubc-club-alerts.md) and the [Databricks plan](databricks-plan.md). Start with the first two for a demo that uses the existing event feed.

1. **Databricks: a public view over real events.** Verify the Bronze export and last sync. Connect the notebook's Silver/Gold outputs to real Quad listings with organizer IDs, publication state, and a verified source URL per event. Keep pending, cancelled, and private records out of the view. Keep demo fixtures separate and label data freshness.
2. **Genie: try a new club.** Ask, “Give me three free events this week from three different organizers.” Genie should return a varied shortlist from Quad's existing listings, with the organizer, date/time, and source link for each. Use Vancouver time, confirmed free admission, and one result per organizer ID. If fewer than three qualify, show the available matches. Test it in the [Genie space](databricks/genie/instructions.md) before adding any chat UI to Quad.
3. **Alerts: finish the test inbox loop.** The backend has subscription and delivery endpoints. The plan still calls for an n8n workflow export and an end-to-end check: one event alert on replay, one room correction to original recipients, and no message after unsubscribe. Start with a test inbox.
4. **Organizer intake: expose the existing API in the website.** Add a small flyer or caption submission flow with a preview and a way to confirm missing details. Keep intake credentials server-side. The current review inbox is for operators.
5. **Later: duplicate evidence and coverage.** Wire asynchronous Databricks match suggestions into the existing review flow and test recurring events and late results before relying on the model. Add a small dashboard for source coverage, missing fields, and the last successful sync. A public Genie endpoint can wait until its data access and fallback have been tested.

For a four-person team: one person can own the website and demo, one can own source checks and enrichment, one can own backend and alert verification, and one can own the Databricks view and Genie. Rehearse together with one real listing: find it in Quad, open its source, then find it again with Genie.
