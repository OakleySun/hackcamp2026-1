# UBC Club Alerts

HackCamp 2026 build plan for a web app that tells UBC Vancouver students about club events they would actually go to.

## 1. Problem and first release

A first-year commuter wants free beginner tech events after class. The AMS calendar is a starting point, and clubs also publish announcements through their own channels. Students often have to know which clubs to follow before they hear about an event. Club Alerts lets them follow interests across the sources we cover and keeps each event linked to its original announcement. [AMS Club Directory](https://www.ams.ubc.ca/student-life/clubs/campusbase/) · [AMS events calendar](https://amsclubs.ca/all-events/)

The project takes inspiration from **dibs**, which turns scattered announcements into listings and alerts. Our campus version tracks multiple announcements about the same occurrence and tells students when a confirmed change affects their plans. [dibs on Devpost](https://devpost.com/software/dibs-8upsd4)

**Student promise** — Pick your interests and constraints, browse matching events, and get one alert when a new match is published. If the organizer confirms a different date, time, or venue, receive a correction linked to the same event. The feed puts the most relevant events first and regularly suggests a beginner-friendly event from a topic you have not picked, so trying something new takes no extra searching.

### What counts as done

- [ ] A student can browse upcoming events, choose filters, and opt in to email alerts.
- [ ] The Discover feed shows a **For You** list ranked by relevance, each card with a plain-language reason, and a **Try something new** row of events outside the student's topics that still respect their practical filters.
- [ ] A participating organizer can submit a flyer or caption, see the extracted draft, and confirm details that need review.
- [ ] A matching event sends one announcement. A repeated intake request and a second source for the same occurrence leave the announcement count at one.
- [ ] A conflicting room stays in review until confirmed. Confirmation updates the same event page and sends one correction to the subscribed students who received the original.
- [ ] Every event links to its source, and the interface shows when a detail is unknown.
- [ ] The team can run the entire flow with labeled sample data and a test inbox.

Start with UBC Vancouver, the AMS calendar where automated access is permitted, and one or two participating clubs. Put direct submissions first. Add an official Instagram connector only if the team already has an eligible professional account and the required access. The coverage page should show which sources are connected and when they last checked successfully. [Meta Instagram API documentation](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api)

## 2. Student and organizer experience

| Screen | What it should do |
| --- | --- |
| **Discover** `/` | Show topic chips, **Free**, **Beginner-friendly**, **After 4 p.m.**, and a **Comfort zone** control (**Stay close**, **Mix it up**, **Surprise me**). Lead with a **For You** list ranked by relevance and a **Try something new** row, then the full chronological **Upcoming** list. Each card shows title, club, local date and time, venue, price, a short reason label (for example *Because you picked Tech* or *New for you: Arts*), **Save**, **Not interested**, and an **RSVP** or **View source** button. Keep the selected filters and comfort-zone setting when the student returns from a detail page. |
| **Event** `/events/{event_id}` | Show the current details, source links, and latest update. For a correction, show the old and new values and when the change was confirmed. Render a missing value as **Not listed** or **Time TBD**. |
| **Get alerts** `/subscribe` | Collect email and filter choices, explain when emails go out, and show a confirmation step. Add a manage or unsubscribe link to each email. Keep browsing available without a subscription. |
| **Submit an event** `/organizer/submit` | A club organizer selects their club, adds a source link, pastes the caption or uploads a flyer, and checks the draft before publishing. Access is limited to invited organizers and the team. |
| **Review queue** `/organizer/review` | Show the existing event, incoming evidence, and what changed. Give the reviewer **Link to event**, **Create separate event**, **Confirm change**, and **Reject** actions as appropriate. |
| **Coverage** `/sources` | List the sources connected for the pilot and their last successful check. Label sample sources as demo data. |

Use a text label on every status chip, a visible focus state on every control, and full labels on filters and form fields. Provide an empty state with **Clear filters** and a useful confirmation message after subscribing. Check the feed and event page on a phone early.

## 3. Architecture and ownership

**Suggested stack** — FastAPI and Pydantic, server-rendered Jinja pages with a small amount of JavaScript, and SQLite on a persistent disk for the single-instance MVP. n8n owns alert matching and delivery. Gemini handles extraction. Add Maritime source monitoring and Databricks reconciliation after the core workflow works locally.

```text
Club submission / approved source checked by Maritime
    -> FastAPI intake -> store source version -> Gemini extracts candidate
    -> validate -> find matching event in SQLite or Databricks SQL
    -> review ambiguous matches or material conflicts
    -> publish event revision and queue its alert in one SQLite transaction
    -> n8n matches recipients -> claim delivery -> test inbox or email
Student website reads current event and source history from FastAPI
```

SQLite owns the current public event, reviews, subscribers, and delivery state. Databricks stores source versions and event snapshots and participates in finding matching events once enabled. A Databricks outage falls back to local matching. Subscriber email addresses stay in the application and delivery path, separate from model input, source monitoring, and the analytics tables.

Recommendations are a deterministic ranking function in FastAPI. They read published events plus a profile the browser sends with each request, store no per-student history, never read subscriber emails, and never send alerts.

| Workstream | First deliverable | Integration handoff |
| --- | --- | --- |
| App and data | Intake, schema, source dedupe, review and publish, recommendation scoring | Stable event and revision IDs, fixture files, endpoints for the website and n8n |
| Website | Responsive feed with **For You** and **Try something new**, event details and subscription form | Connect to the seeded API and `POST /api/recommendations` first, then test a real signup and correction |
| Extraction and sources | One flyer through Gemini, then one monitored source through Maritime | Validated candidate fields with evidence and a stable source ID |
| Automation and submission | n8n test inbox, delivery log, research interviews and demo | One announcement, one correction, source trace and Devpost write-up |

## 4. Step-by-step build

### Step 0 — Lock the demo and repo layout

1. Assign the workstreams and agree on the API shapes below before splitting up.
2. Ask a few students how they currently find club events and a club organizer how they communicate venue changes. Record actual examples with permission. Pick one student persona and one organizer for the pitch.
3. Fix the topic list and its adjacency map before anyone builds, because Gemini classifies into it, n8n matches on it, the recommender uses it, and the feed renders it as chips. Proposed slugs: `tech`, `career`, `academic`, `arts`, `sports`, `culture`, `social`, `wellness`. Keep them in `fixtures/topics.json` (see Step 5).
4. Create a fictional **Intro to Git** workshop and a test subscriber who chooses **Tech**, **Free**, **Beginner-friendly**, and **After 4 p.m.** Use the same fixture across the backend, site, n8n, and demo.
5. Create the following files as the team implements each step.

```text
app/                 FastAPI routes, models, matching, recommendations and storage
app/templates/       Student and organizer pages
app/static/          Styles and browser assets, including the local profile script
fixtures/            Topic list, labeled flyer, caption, mirror, correction and test events
scripts/             Database init, local demo runner and worker
sql/                 Databricks Delta tables and reconciliation query
workflows/           n8n export with credential references removed
tests/               Intake, matching, revisions and delivery tests
.env.example         Variable names and placeholders
requirements.txt     Python dependencies
```

**Exit check** — Everyone can describe the first demo and has the same fixture, field names, and working branch boundaries.

| Fixture | Input | Expected state |
| --- | --- | --- |
| A — original flyer | Fictional Intro to Git workshop. Nov. 12 at 5 p.m., Demo Hall 101, explicitly free and open to beginners. | One event and one announcement for the matching subscriber. |
| B — mirror | Same organizer, workshop, time, room, and event-specific RSVP, published under a different source ID. | Same event and an added source link. No second announcement. |
| C — organizer update | Same workshop and RSVP, with room changed to Demo Hall 204. | Pending review first. After approval, the same event page shows the new room and the inbox has one correction. |
| D — next week | Same title and organizer one week later, with a general sign-up page. | Separate occurrence with its own event ID. |
| E — stretch wildcard | Fictional **Watercolour Night**, `arts`, Nov. 13 at 6 p.m., explicitly free and beginner-friendly. | Not in **For You** for the test subscriber. Appears in **Try something new** as the non-adjacent pick. No alert. |
| F — filtered out | Fictional **Rec Volleyball Drop-in**, `sports`, Nov. 14 at 7 p.m., $5. | Never recommended to the test subscriber because it fails **Free**. |
| G — adjacent stretch | Fictional **Resume Clinic**, `career`, Nov. 13 at 4:30 p.m., free and beginner-friendly. | Appears in **Try something new** labeled as close to Tech. No alert. |

Add a second subscriber who follows a different topic and a third who unsubscribes after the first alert. Use the real future fixture date for HackCamp or shift all fixture dates together for later rehearsals.

### Step 1 — Set up the local app and data

1. Install or select Python 3.11 or later. Use FastAPI, Uvicorn, Pydantic, Jinja2, `python-multipart`, `httpx`, `python-dotenv`, `google-genai`, `tzdata`, and `pytest` in `requirements.txt`. Add `email-validator` if using Pydantic’s `EmailStr`.
2. Add `.env`, `.venv/`, `data/`, and local uploads to `.gitignore`. Commit fictional fixtures and the env template. Load real credentials into the service that needs them.
3. Initialize a SQLite schema with foreign keys, unique constraints, and short transactions. Use one durable intake worker for the MVP. Store local database files outside any stateless container filesystem.
4. Put a seeded list behind `GET /api/events` and return a stable ID per occurrence. Build against the seed before adding external services.

Once the scaffold exists, run from the repo root in PowerShell.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env -ErrorAction Stop
.\.venv\Scripts\python.exe -m scripts.init_db
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Copy `.env.example` only on first setup. Once the worker is implemented, start `.\.venv\Scripts\python.exe -m scripts.worker` from a second terminal. Check the API with `Invoke-RestMethod http://127.0.0.1:8000/health`.

Keep the database and fixture defaults in the local profile. The example config should document `APP_BASE_URL`, `DATABASE_PATH`, `APP_MODE`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `SOURCE_INGEST_TOKEN`, `N8N_WEBHOOK_URL`, `N8N_WEBHOOK_SECRET`, `WORKFLOW_API_TOKEN`, `DATABRICKS_HOST`, `DATABRICKS_WAREHOUSE_ID`, `DATABRICKS_CATALOG` and `DATABRICKS_SCHEMA`. Document the chosen Databricks authentication variables alongside those. The n8n email API key belongs in its credential store.

| Record | Fields or constraints that matter |
| --- | --- |
| `clubs` | Stable club ID, display name, known aliases, official links. Canonicalize names through a small curated alias map. |
| `topics` | Stable slug, display label and adjacent topic slugs, loaded from `fixtures/topics.json`. Event topics and subscription topics must use these slugs. |
| `sources` | Source ID, club or calendar, kind, allowlisted URL, enabled flag, last successful check. |
| `source_announcements` | Unique source/version identity, source URL, content hash, caption or private asset ref, detected time, extraction status, validated fields, evidence and linked event ID. |
| `events` | Stable event ID, organizer, current revision, publication state, current values and provenance. Allocate one ID per occurrence. |
| `event_revisions` | Unique `(event_id, revision)`, snapshot, previous values for changed fields, reason, approver and timestamp. |
| `review_items` | Incoming source version, candidate event IDs, expected revision, field diff, reviewer and decision state. |
| `subscriptions` | Subscriber ID, email, topic IDs, filters, verification and opt-out timestamps, token hashes. |
| `event_outbox` | Unique `(event_id, revision, kind)`, pending or complete status, attempt count and retry time. |
| `deliveries` | Unique `(subscriber_id, event_id, revision, kind)`, stored message payload, attempt state, claim expiry and provider message ID. |

**Exit check** — A fresh local DB starts, `GET /health` returns 200, and a seeded upcoming event appears in the feed on desktop and mobile.

### Step 2 — Intake and Gemini extraction

1. Implement an authenticated intake route for source connectors and an organizer form for direct submissions. Accept text and JPEG or PNG images up to a documented size cap such as 5 MB. Validate decoded file type, size, club scope, and allowed source links. Keep the uploaded image private to the review workflow unless you have permission to republish it.
2. Normalize the source ID and calculate a content hash from the stable content fields and image bytes, excluding polling timestamps. Uniquely identify a version by `(source_id, external_id, content_hash)`. An unchanged retry returns the existing ID. A revised post creates a new version and keeps its previous evidence.
3. Return `202 Accepted` after persisting an intake job. Have the worker resume pending jobs, including interrupted extraction. Route permission errors, unsupported images and repeated failures to review with a reason.
4. For a flyer or caption, call Gemini with image bytes plus text and a small structured-output schema. Pick an image-capable model in your project and set it via `GEMINI_MODEL`. Allow nulls for unknown fields. Constrain `topics` to the slugs in `fixtures/topics.json` as an enum, with one or two per event. Ask for short source excerpts for date, time, venue, cost and eligibility. Treat flyer text as source material and run the model with no action tools. [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output?lang=rest) · [Gemini image input](https://ai.google.dev/gemini-api/docs/image-understanding?hl=en)
5. Validate parsed values in Pydantic and apply server rules. Require a recognized organizer, title and known local date to publish. A date-only listing can show **Time TBD** and stays out of the alert workflow until a valid start time is available. Use `America/Vancouver` for local dates and time filters and store known instants in UTC. Keep time zone data current and route ambiguous or contradictory times to review.
6. Use `cost_status` values `free`, `paid`, and `unknown`. Mark an event free for the general audience only with explicit evidence. Use `true`, `false`, or `null` for `beginner_friendly`. Leave absent venue, end time, cost, and RSVP URL blank. Only accept RSVP URLs found in the source or supplied by the organizer, and offer **View source** when the RSVP link is missing.
7. For structured calendar listings, parse explicit page fields first. Send unclear records to the same validator and review path. Use one intake contract regardless of source.

**Example candidate for fixture A**

```json
{
  "organizer_slug": "demo-campus-coding-club",
  "title": "Intro to Git",
  "local_date": "2026-11-12",
  "local_start": "17:00",
  "local_end": "18:00",
  "timezone": "America/Vancouver",
  "venue": "Demo Hall 101",
  "cost_status": "free",
  "beginner_friendly": true,
  "topics": ["tech"],
  "rsvp_url": "https://example.org/rsvp/demo-intro-to-git"
}
```

The fixture is fictional. For a clickable demo, point the RSVP link to a labeled sample RSVP page on the demo deployment.

**Exit check** — The same fixture can be posted twice with one source version. Gemini returns a plausible draft, and a flyer with no cost shows **Not listed** and fails the **Free** filter.

### Step 3 — Reconcile events and approve corrections

1. Look up any prior version of the same source record to find its linked occurrence. For a new source, first look for an exact event-specific RSVP URL and corroborating organizer and date. Strip known tracking parameters and fragments while preserving query parameters that identify the event.
2. If no specific link matches, compare club ID, normalized title, and scheduled occurrence. Use exact normalized matches for automatic linking. Queue multiple candidates, close-but-different titles, shared general sign-up URLs with conflicting dates, and other ambiguous cases for review. Distinct sessions of a recurring event get different IDs.
3. Attach a duplicate source to the existing event and record the evidence. An unchanged display record keeps its revision and queues zero alerts. Allow corroboration to fill an empty field through the normal publish rules. A link or wording change alone does not generate a correction alert.
4. Keep the public snapshot in place when a new source conflicts on date, time, or venue. Show the diff and evidence to the club organizer or a team reviewer. Confirm against the expected current revision so an older review cannot overwrite a newer change. A stale repost of the old details cannot roll back a confirmed correction.
5. In one SQLite transaction, persist the accepted event revision and any notification outbox row. Emit `new_event` once when the event first becomes eligible for alerts. Emit `correction` for a subsequent confirmed change to the date, time, or venue. Save the old and new values for the correction message. Treat other edits as quiet updates.

**Exit check** — Source A publishes event E. Source B, a mirror of A, links to E with no new alert. Source C reports a new room and queues a review. After confirmation, E displays the new room and queues one correction. A repeat of the original source leaves E unchanged.

### Step 4 — Wire up student subscriptions and n8n

1. Connect the event feed and subscribe form to the API. Show upcoming results sorted by local start time and shareable filter values in the URL. Use the same matching fixtures to verify both feed and workflow behavior.
2. Collect explicit email opt-in and verify ownership with a single-use, expiring token. Provide a signed or opaque manage link and an unsubscribe action. Rate-limit signup and verification requests. For the first local loop, use fictional subscribers and a capture inbox.
3. Set up a local n8n instance with persistent storage or use a team n8n Cloud workspace. In local Docker, connect n8n to FastAPI via a shared Compose network, or via `host.docker.internal` when the API runs on the host and is reachable from Docker Desktop. For n8n Cloud, give the workflow an authenticated HTTPS API endpoint it can reach. [n8n installation](https://docs.n8n.io/deploy/host-n8n/install-options/install-using-docker-compose.md)
4. Create a **Webhook** with header authentication and the path `club-alert-revision`. Configure `X-Club-Alerts-Webhook-Key` in its Header Auth credential and send the same secret from `N8N_WEBHOOK_SECRET`. Use its Test URL while developing, then publish the workflow and set `N8N_WEBHOOK_URL` to its Production URL. The outbox posts the event ID, revision, and kind. [n8n Webhook node](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/)
5. Add **HTTP Request → Code → Loop Over Items → HTTP Request** to read the revision and candidate subscribers, match them, and claim each delivery. A new event matches when at least one selected topic overlaps (or all topics are selected) and all enabled filters pass. For **After 4 p.m.**, define the boundary as 4:00 p.m. inclusive in Vancouver time. Corrections go to still-subscribed recipients of the original alert even if the revised event falls outside their filters.
6. Make the claim atomic and recheck unsubscribe, publication status, and any prior successful send before returning recipient and message fields. Send via a test sink first, then use the team’s test email provider credentials. Set a stable provider idempotency key, for example `club-alert/<delivery_id>`, and reuse the same payload on retries. Save provider acceptance and its message ID separately from an inbox delivery receipt. Resend is one possible provider and retains idempotency keys for 24 hours. [Resend idempotency documentation](https://resend.com/docs/dashboard/emails/idempotency-keys)
7. Use **Respond to Webhook** after the loop. Return success when all applicable deliveries are accepted, skipped, or marked terminal. Return a retryable result if any applicable delivery is pending, leased by another execution, or failed transiently. Retry incomplete jobs from the durable outbox with backoff. Use a lease for abandoned claims and cap automatic retries inside the provider’s idempotency window. Send unresolved outcomes to a manual review queue after the retry deadline. Process jobs for the same event in revision order so a correction cannot overtake the original alert.
8. Export the workflow without secrets. Keep example text and IDs fictional, and limit retention of execution payloads containing addresses.

**Alert copy**

- **New event** — “Intro to Git · Thursday at 5 p.m. · Demo Hall 101. Free and beginner-friendly. View event or RSVP.”
- **Correction** — “Room change for Intro to Git. Demo Hall 101 → Demo Hall 204. The event still starts Thursday at 5 p.m. View updated event.”

**Exit check** — Replay the webhook twice and see one captured announcement. Confirm the room change and see one correction. An unmatched or unsubscribed test student receives zero alerts.

### Step 5 — Recommendations: For You and Try something new

The feed answers two questions: what is this student most likely to want, and what might they enjoy that they would not have picked themselves. Both lists come from one deterministic scorer in `app/recommend.py`, so every result is explainable, testable with fixtures and stable during the demo. No model call is needed.

1. **Profile.** Build the profile in the browser from the topic chips and filters in the URL, the comfort-zone setting, and a short interaction history in `localStorage` under a random anonymous profile ID. Record `view`, `source_click`, `save`, `rsvp_click` and `dismiss` with event ID, topics, club ID and timestamp, keeping the latest 200 entries. Send the profile with each call to `POST /api/recommendations`. The server uses it for that request only and stores no per-student history, and subscriber emails never enter this path. Wrap storage access in try/catch and fall back to URL-only ranking when storage is unavailable.
2. **Eligibility.** Start from upcoming published events. Drop past events, events the student dismissed, and anything that fails an enabled hard filter. **Free**, **Beginner-friendly** and **After 4 p.m.** apply to both lists with the same strict unknown-value rules as alerts, because they describe what the student can actually attend. Exploring stretches topics, not logistics.
3. **Affinity.** Score each topic from history: `view` +0.5, `source_click` or `save` +1, `rsvp_click` +2, `dismiss` −1, each weighted by a 14-day half-life. Score clubs the same way from `save` and `rsvp_click` only.
4. **For You score.** Rank eligible events by these points, then by start time.

   | Signal | Points |
   | --- | --- |
   | At least one event topic is among the student's selected chips | +3 |
   | Highest affinity among the event's topics | up to +2 |
   | Club the student saved or RSVP'd before | +1 |
   | Starts within 3 days, or within 7 days | +1, or +0.5 |
   | `beginner_friendly: true` or `cost_status: free` while that filter is off | +0.5 each |

   An event enters **For You** only with a selected-topic match or a topic affinity of at least 1. With no selections and no history, hide **For You** and show **Upcoming** with a prompt to pick topics.
5. **Stretch candidates.** An event is a stretch when none of its topics is selected and each of its topics has affinity below 1. Give +1 when `beginner_friendly` is true, since a newcomer-friendly event is the easiest way into a new scene, +1 when a topic is adjacent to a selected topic in `topics.json`, and the same soonness points. Fill **Try something new** with up to three, at most one per topic, and include one non-adjacent wildcard when one exists so the row is not always the nearest neighbour.
6. **Comfort zone.** **Stay close** shows the stretch row below **For You** only. **Mix it up**, the default, also places one adjacent stretch event as every sixth **For You** card. **Surprise me** places one every third card and allows wildcards in those slots. Every stretch card carries a **New for you** label and its reason so it never reads as a bad match.
7. **Stable variety.** Break ties among stretch events with a shuffle seeded by the anonymous profile ID and the Vancouver local date. The row stays put on refresh and changes from day to day. In `APP_MODE=demo`, use a fixed seed so rehearsals match.
8. **Learning from it.** Stretch interactions update affinity like any other. When a stretch topic reaches affinity 2, offer a one-tap **Add Arts to my topics** prompt for that topic. A dismissal lowers the topic's affinity, and the half-life lets it return later.
9. **Alerts stay predictable.** Recommendations shape the feed only. Email alerts keep the subscription matching from Step 4, and stretch events never trigger an alert.
10. **Measure.** Keep anonymous aggregate counters of stretch impressions, clicks and topic additions per comfort-zone setting, with no profile IDs, as pilot evidence.

**Reason labels**

- *Because you picked Tech*
- *You've saved 2 Career events*
- *From a club you've RSVP'd to*
- *New for you: Career · close to Tech · free*
- *New for you: Arts · free and beginner-friendly*

**Exit check** — With the test subscriber's choices and an empty history, Intro to Git leads **For You** with *Because you picked Tech*. **Try something new** shows G as an adjacent pick and E as the wildcard, and F never appears. After a save and an RSVP click on E, the **Add Arts to my topics** prompt appears. Refreshing keeps the same row, and the test inbox receives nothing for E or G.

### Step 6 — Deploy a Maritime source-monitoring agent

1. Add a small source-check script that fetches only configured sources with permitted access. Start with a team-owned, hosted fixture feed. Check AMS access requirements and use an available supported feed or permitted pages for real monitoring. Use manual intake when automated access is unavailable.
2. Have the script emit one structured record per listing with the source ID, external listing ID, canonical URL, observed time, and caption or attachment reference. Save run status, counts, and errors. Distinguish a failed fetch from an empty result. A disappeared listing is a review signal and does not automatically cancel an event.
3. Deploy a Maritime agent template with terminal tools. Put the checker script and read-only source list in its workspace. Configure the HTTPS app endpoint and a credential scoped to intake. Give the agent the fixed command to run and require a run summary with detected, submitted, unchanged, and failed counts. Page content stays data for the checker and cannot set commands or destinations. [Maritime agent frameworks](https://maritime.sh/docs/frameworks)
4. Run it manually against the demo feed and verify the intake request reaches the app. Configure a Maritime platform trigger for each 15-minute check. The platform trigger can wake an idle agent. Replace `club-alerts-monitor` with the actual agent ID if it differs. [Maritime triggers and schedules](https://maritime.sh/docs/triggers)

```powershell
maritime triggers create club-alerts-monitor --type cron --cron "*/15 * * * *" --prompt "Run the approved club source-check script and report detected, submitted, unchanged and failed counts."
maritime triggers list club-alerts-monitor
```

5. Add a new fixture listing to the hosted feed. Capture one real scheduled run and keep its timestamp and corresponding intake record for judging. Keep a manual **Run check** path for a deterministic live demo.

**Exit check** — A real Maritime run discovers a labeled demo listing. Rechecking the same source yields no additional event or alert. The team can show the deployed agent and its run history.

### Step 7 — Add Databricks SQL reconciliation

1. Check access early. In the team workspace, start a SQL warehouse, note its ID, and run `SELECT 1` using the same app-side authentication you plan to demo. Give that identity permissions for the selected catalog and schema. Keep warehouse ID, host and credentials on the backend. [Databricks Free Edition limits](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations) · [Statement Execution API tutorial](https://docs.databricks.com/aws/en/dev-tools/sql-execution-tutorial)
2. Create two Delta tables in a team-selected schema. Keep DDL and the reconciliation query in `sql/`.

   | Table | Logical key and data |
   | --- | --- |
   | `source_announcements` | `announcement_id` per source version, source ID and URL, detection time, normalized organizer and title, local date and start time, RSVP key, validated fields, linked event ID, and match or conflict outcome. |
   | `event_records` | `(event_id, revision)`, current snapshot values, normalized matching fields, state, and published timestamp. Derive the latest snapshot per event with a window function. |

3. Write source rows and accepted event snapshots with keyed `MERGE` statements so retries can update the same logical row. Use a small durable projection queue in SQLite. Send parameterized statements and poll incomplete responses by statement ID. Keep failed projections queued until the warehouse is available.
4. Before Databricks matching, flush the pending projections and upsert the incoming source version. Query current snapshots in SQL. Join by organizer and rank an event-specific RSVP match above an exact normalized title and occurrence match. Return candidate IDs and conflicting fields, including a venue difference. If the warehouse is unavailable or the projection is behind, log the fallback and run the local matcher. Apply the result to the authoritative SQLite state with a revision check.
5. Link the incoming source to the accepted event ID after the review or publish step and project the updated row. Save a query that shows source A and source B linked to one event, with C flagged for a venue change. Show revision 2 after approval.

**Exit check** — Databricks actually produces candidate matches for a demo run. Two announcements link to the same event, the changed venue is visible in the SQL result, and a forced warehouse timeout leaves the app functional.

### Step 8 — Deploy, test, and rehearse

1. Deploy FastAPI behind HTTPS on a service with a persistent disk, one app instance and one worker. Mount SQLite and private assets on the disk. Configure the production n8n URL, provider credentials, and auth tokens. Bind source and workflow tokens to separate privileges. Restrict organizer review to the owning club or team reviewers. Keep browser sessions, CSRF protection and secure cookies on organizer actions.
2. Run a clean deploy with `APP_MODE=demo` and a dedicated demo DB and test inbox. Gate fixture reset behind team authentication, and require separate configuration for any pilot delivery. Enable email verification and unsubscribe before inviting students to a pilot.
3. Smoke-test from a phone on cellular and from Maritime and n8n. Verify the site, source URL, sample RSVP, signup, alert and correction. Keep a screenshot of the successful SQL query and Maritime run plus a short recording of the end-to-end flow.
4. Record detection, publication, and provider-acceptance times. Track how many duplicate deliveries were suppressed in the test set. Ask pilot participants whether they saw a relevant event they would otherwise have missed, and report counts with the sample size.

## 5. API handoff

| Endpoint | Caller and contract |
| --- | --- |
| `GET /health` | Liveness check. Returns basic app state without exposing configuration. |
| `GET /api/events` and `GET /api/events/{id}` | Public feed and latest published detail. Include only public metadata and source links. |
| `POST /api/recommendations` | Public and rate-limited, with no personal data. Accepts selected topics, filters, comfort-zone setting, anonymous profile ID and the browser's interaction history. Returns `for_you` and `try_something_new` lists of event IDs, each with score, `kind` (`match` or `stretch`) and reason label. Stores nothing per student. |
| `POST /api/subscriptions` | Public opt-in. Validate filters, create pending subscription, and trigger verification. |
| `GET /verify` and `POST /verify` | Show an email confirmation form, then consume its expiring verification token when submitted. |
| `GET /manage` and `POST /manage` | Show preferences for the token holder, then apply submitted updates or opt-out. |
| `POST /api/intake` | Scoped connector token for JSON metadata, or organizer session for the direct form. Accept `source_id`, `external_id`, `source_url`, `observed_at` and text or an approved attachment. Return `announcement_id` and processing state. |
| `POST /api/reviews/{id}/resolve` | Authorized organizer or team reviewer sends decision and expected event revision. Return `409` if the event changed while the review was open. |
| `GET /internal/dispatch/{event_id}/{revision}/{kind}` | Workflow token only. Returns revision and candidate subscriber IDs and preferences. The dispatch key identifies one outbox row. |
| `POST /internal/deliveries/claim` | Workflow token only. Atomically claim by subscriber, event, revision and kind. Return a claim token and stored send payload for an eligible unsent delivery. |
| `POST /internal/deliveries/{id}/result` | Workflow token and current claim token. Records accepted, retryable or terminal result and any provider message ID. |

## 6. Test matrix and fallback plan

| Scenario | Expected result |
| --- | --- |
| Free beginner tech event at 5 p.m. Vancouver time | Matching test student gets one announcement. |
| Start exactly at 4 p.m. or one minute before | 4 p.m. matches the after-class filter. 3:59 p.m. does not. |
| Missing price, member-only free, or missing beginner signal | The corresponding restrictive filter excludes the event. The source is still visible on the detail page. |
| Unchanged duplicate intake, retry or simultaneous webhook | One source version for the duplicate intake and one accepted message for the delivery key. |
| Mirror announcement with same event-specific RSVP | One public event with two source links. No second announcement. |
| Weekly events share a generic RSVP URL | Separate occurrences. If conflicting records look like one moved event, a reviewer decides. |
| Flyer and caption disagree on a room or start time | Review item shows both values and preserves the public event until a decision. |
| Confirm room change twice, then replay original | Same event ID, one correction, new room stays in place. |
| Email provider times out after accepting the send | Retry the same payload and provider key within the retention window. Record one provider message ID. |
| Unsubscribe before a retry | No new send attempt for that recipient. |
| Source unavailable or Gemini output invalid | Preserve the source status or job error. Review manually or use a labeled fixture for the demo. |
| Databricks offline | Local matching and alerts continue. Projection waits for the warehouse. |
| New visitor with no topics and no history | **For You** is hidden. **Upcoming** shows with a prompt to pick topics. |
| Tech selected with **Free** on | Stretch picks exclude paid events and events with unknown cost. |
| Same profile refreshed twice on one day | Same **Try something new** row. It may change the next day, except in demo mode. |
| Student dismisses a stretch event | The event disappears and its topic stops being suggested until affinity recovers. |
| Browser storage blocked | Ranking falls back to URL choices with no error shown. |
| Stretch event published | No email to subscribers whose topics do not match it. |

If a connector is blocked, demonstrate the direct form with the same intake payload. If the venue network blocks email, show the n8n test inbox and its delivery log. Label recorded and sample flows in the demo and report which integrations actually ran. Defer Instagram, extra clubs, model-based or collaborative recommendations, and native push until after the core demo.

## 7. HackCamp execution order

| Elapsed time | Milestone |
| --- | --- |
| Hours 0–2 | Interview students and a club organizer, set up credentials, agree on contracts, and create fixtures. |
| Hours 2–5 | Seed the website and build direct intake plus Gemini extraction. Start n8n against the test inbox. |
| Hours 5–8 | Deliver the first end-to-end alert, then implement duplicate detection, venue review and the correction. Rehearse the core demo. |
| Hours 8–12 | Build **For You** and **Try something new** against fixtures E–G. Deploy Maritime and Databricks in parallel. Integrate each as soon as its smoke test passes. |
| Hours 12–17 | Deploy the app, test failure cases, finish mobile layout and collect pilot observations. |
| Final hours | Freeze features, film one complete run, submit on Devpost and rehearse with the actual demo accounts. |

## 8. Demo and Devpost

### 90-second demo

1. **0:00–0:15.** Open the site as a first-year commuter. Select **Tech**, **Free**, **Beginner-friendly**, and **After 4 p.m.** Point to the **Try something new** row suggesting a free beginner arts night.
2. **0:15–0:35.** Run the Maritime check against the labeled demo feed, or submit the fixture directly. Open the flyer beside the Gemini draft and publish it. Show it at the top of **For You** with *Because you picked Tech*, then the incoming announcement and its RSVP link.
3. **0:35–0:55.** Feed in a mirror listing. Show two sources linked to one event in Databricks and one announcement in the inbox.
4. **0:55–1:20.** Submit a room update. Show the review diff, approve it, refresh the same event page, and open the single correction email.
5. **1:20–1:30.** Show what is covered today and name one piece of pilot evidence or a metric measured during the demo.

### Track checklist

| Track | What to include if completed |
| --- | --- |
| **Community Impact** | Opt in and explain who misses club events, what you heard in interviews, how **Try something new** helps students find clubs outside their usual circle, and what the pilot can measure. |
| **Best Use of Gemini API** | Show a real image extraction and an example where an absent field stays blank. |
| **Best Use of n8n** | Show the workflow, filtered recipients, one announcement and one correction. |
| **Best Agent on Maritime** | Show the deployed agent and source check. Include a short demo in the submission. |
| **Best Use of Databricks** | Show the Delta records and the SQL reconciliation of a duplicate and a room change. |
| **Best Project Built with Freebuff** | If used during HackCamp, opt in and describe a feature it helped implement or test, with a concrete before-and-after result. |

Prioritize Community Impact, Gemini and n8n. Add Maritime and Databricks entries once the team can show each one working. Link the app, repository and short demo. Credit dibs and the connected data sources, label fictional fixtures, and include one honest coverage statement. [HackCamp prize and submission criteria](https://hackcamp-2026.devpost.com/#prizes)
