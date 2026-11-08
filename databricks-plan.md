# Plan: Make Databricks the campus events intelligence layer of UBC Club Alerts

## Goal and scope

Use Databricks to turn scattered club announcements into a trustworthy, searchable picture of campus life. Preserve the original evidence, assist reviewers with semantic duplicate detection, let students ask questions through Genie, and show organizers gaps within the event sources we cover.

The current app has local matching and SQLite event revisions; Databricks currently appears in two hand-run SQL files. This plan connects Databricks to the working application through a durable background pipeline.

The [HackCamp workshop](https://github.com/databricks-solutions/data-intelligence-for-smarter-community) is a useful reference for Bronze -> Silver -> Gold and Genie. The distinctive result is reliable event identity across differently worded posts and confirmed changes, backed by source provenance and reviewer decisions.

**Required deliverable:** one reliable pipeline, one demonstrated semantic duplicate review, Genie answering tested questions, and one useful dashboard.

**Decisions**

- SQLite remains authoritative for publication, reviews, subscriptions, event revisions, and alert delivery.
- Databricks handles asynchronous enrichment, match suggestions, curated query tables, and analytics.
- Potential semantic duplicates stay unpublished in review while enrichment runs. An AI suggestion never links, publishes, or changes an event automatically.
- All Databricks network requests run outside SQLite write transactions and outside intake/review request handling.
- Genie appears in the existing website. A separate Databricks map app and Vector Search are deferred.
- Keep the existing Gemini extraction and topic vocabulary. Do not add a second mandatory classifier for fields already validated by the backend.
- Establish timing after the first working integration slice. The previous 8-12-hour estimate for the full proposal was optimistic; reserve explicit time for authentication, integration, failure handling, and rehearsal.

**Demo story:** "Two club posts describe the same event differently. Databricks helps us identify the duplicate, a reviewer confirms it, and students can search the resulting trustworthy event data in plain language."

## Hosting and data ownership

- Keep the existing website on its current host. Run FastAPI and one background worker against SQLite on the same persistent host and database path. Render or Railway with persistent storage are possible choices; inspect current hosting and disclose costs before provisioning anything.
- Keep an independently usable local demo until the backend has a reachable HTTPS origin. SQLite must live on persistent storage when deployed.
- Keep credentials server-side. Subscriber emails, verification tokens, message payloads, and user profiles stay out of Databricks and model inputs.
- Public query credentials should have read access only to curated public gold tables and the relevant Genie space. Give the export worker separate write access to bronze and read access to match results; the pipeline identity owns its transformations.

## Phase 0: Prove workspace access before building

Time-box an initial access check to 30-60 minutes. Record actual results rather than assuming a feature or endpoint exists.

- [ ] Execute `SELECT 1` through the SQL Statement Execution API using the intended backend authentication.
- [ ] Identify the serverless warehouse and create schemas under an accessible catalog, for example `workspace.club_alerts_bronze`, `workspace.club_alerts_silver`, and `workspace.club_alerts_gold`.
- [ ] Run one structured `ai_query` request on an available model and validate its output. Discover the model endpoint in the workspace instead of hardcoding an example model name.
- [ ] Create a Genie space over a tiny public table and complete an API question through to its query results.
- [ ] Verify permissions for the export, transformation, and public-query identities. Keep a public Genie proxy disabled until its public-data access boundary works.
- [ ] Run one Lakeflow Job manually and confirm the available scheduling and compute quotas.
- [ ] Record quota behavior, expected job latency, the last successful sync, and the fallback demonstration.

[Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations) include quota-driven compute shutdowns. Databricks Apps also stop after 24 hours; Apps are deferred and are not a prerequisite for this release. Do not upgrade to paid resources without discussing the cost.

**Exit check:** authenticated SQL, one structured model judgment, and one Genie question work in the actual workspace. If one fails, reduce the deliverable explicitly before adding more features.

## Phase 1: Durable background export to Bronze

1. Add `app/databricks.py`, a small `httpx` client for parameterized SQL statements, bounded polling, and retrieval by statement ID. Support the verified authentication method. Retain statement IDs after timeouts so the worker can reconcile an in-flight operation before resubmitting it.
2. Add `dbx_queue` and `dbx_match_jobs` through the schema and an idempotent migration for existing SQLite databases. The export queue records a unique operation key, kind, aggregate/version, payload, state, attempts, claim expiry, next retry time, and a safe error. Match jobs track announcement identity, candidate event IDs/revisions, model/prompt version, and results.
3. Enqueue raw source versions when intake saves them; enqueue validated evidence, processing/review outcomes, and event revisions when those local records change. The local mutation and its queue row commit in the same SQLite transaction, including early review-return paths.
4. Add `scripts/dbx_worker.py`. It claims work in a short transaction, closes the transaction, calls Databricks, then opens a short transaction to record success or schedule a retry. Expired claims are recoverable after a crash.
5. Use idempotent `MERGE` operations keyed on `announcement_id`, `(event_id, revision)`, and assessment request ID. Export pending match jobs to `bronze.match_requests` before expecting a pipeline judgment. For mutable announcement projections, attach a monotonic projection version and reject older updates so a delayed retry cannot overwrite a newer review outcome.
6. Do not call `flush_dbx_queue()` from intake, review resolution, or inside `service.process` write transactions. Wrapping a synchronous call in `try/except` would still delay requests and hold locks.
7. When Databricks is unconfigured, expose an explicit disabled state and preserve the current local workflow. Enable semantic-review holding separately with `DATABRICKS_MATCH_MODE=review`; existing pending reviews always remain available for manual resolution.

Bronze tables:

| Table | Purpose |
| --- | --- |
| `bronze.source_announcements` | Original caption, stable source/version identity, detected time, source URL, validated Gemini candidate, evidence, and current processing outcome. Keep original evidence separate from enrichment. |
| `bronze.event_revisions` | Immutable event snapshots keyed by `(event_id, revision)`, changed fields, publication state, reason, approval time, and source references. |
| `bronze.match_requests` | Requested announcement/candidate pairs, source hash, expected event revisions, and model/prompt version, keyed by assessment request ID. |

Start with fixtures A-C and a small labeled set of differently worded duplicate and separate-occurrence examples. Expand toward 80 fictional events only after the real export path works. Label all generated data as demo data and move fixture dates together for later rehearsals.

**Exit check:** intake returns independently of Databricks availability; a worker restart safely resumes queued work; replay creates no duplicate rows or stale overwrites.

## Phase 2: Curate Silver and Gold

Keep SQL in `sql/`. Run one Lakeflow Job on demand during development, then every 10 minutes if workspace quotas permit. This is a batch freshness interval, not an immediate intake-matching guarantee.

1. **`silver.announcements`:** parse and validate the exported candidates, retain source evidence, and normalize organizer names, dates, topics, and venue text. Preserve `free`/`paid`/`unknown` and nullable beginner eligibility. Uncertain enrichment cannot establish free admission or beginner eligibility.
2. **Venue normalization:** use a small curated building/alias table when needed for the dashboard. Unresolved locations stay unknown. Full UBC Geodata ingestion, model-based venue inference, and map rendering are stretch work; credit and check the license of any imported data.
3. **`gold.match_judgements`:** evaluate unprocessed candidate pairs in `bronze.match_requests` and return the assessment request ID with each judgment. Use structured output such as `{same_event: true|false|null, changed_fields: [...], reason: string, evidence: [...]}`. A date window is candidate generation, not proof of identity; distinguish recurring sessions and generic RSVP links.
4. Cache each judgment by source content hash, candidate event ID/revision, and model/prompt version. Reuse unchanged judgments; evaluate only new or changed pairs. A failed or invalid model response is an unresolved assessment, not a negative match.
5. **`gold.events_current`:** latest published revision per event, including its source links and freshness metadata. Exclude pending, rejected, and cancelled records from upcoming-event discovery.
6. **`gold.event_history`:** explicit application revisions and their changed fields, reasons, and source evidence. Keep this table independently of Delta transaction-log retention.
7. **`gold.campus_activity` and `gold.opportunity_gaps`:** aggregate published events by topic, known building, weekday, and Vancouver local hour. Describe gaps as shortages among connected sources in the selected period; show coverage, unknown-field counts, and sample size.

**Exit check:** every current gold event traces to its source and application revision, unresolved announcements stay out of public results, and the demo duplicate pairs have inspectable judgments.

## Phase 3: Asynchronous matching and human review

This replaces the proposed synchronous five-second Databricks lookup inside `service.process`.

| Intake situation | Immediate local action | Later action |
| --- | --- | --- |
| Exact source retry or deterministic duplicate | Reuse the existing source/event through local matching. | Export the outcome; no second announcement. |
| Confirmed source identity with conflicting room or time | Keep the published event unchanged and open the existing review flow. | A reviewer confirms or rejects the change. |
| No exact match, but a plausible existing occurrence from the same club within the pilot date window | Save the validated announcement and evidence, open a review labeled `awaiting_semantic_match`, and atomically queue its assessment. Create no public event or alert yet. | Databricks supplies evidence for the existing review; the reviewer chooses link, separate occurrence, confirm change, or reject. |
| No plausible existing occurrence | Continue the normal local new-event path. | Export the source and event revision. Reassess candidate-window coverage during evaluation. |

For the pilot, use same-club events within +/-1 day as a conservative candidate window, including the existing local similar-title review cases. A changed known source record keeps its prior-event identity even outside this window. Measure misses and false positives before widening the rule.

- Persist the requested announcement content hash and each candidate revision before export. An assessment does not depend on the incoming announcement already having a public event ID.
- After a completed pipeline run, the worker imports results outside any write transaction. Apply them locally only if the review is still open and the source hash and candidate revisions still match; otherwise discard/requeue the stale assessment.
- Store the model suggestion, evidence, and reason separately from the reviewer decision. Show them in the review API/UI. Support choosing the intended candidate when several are listed.
- On approval, recheck the selected event revision inside a short transaction. Update the source link, event revision if needed, alert outbox, and Databricks export queue atomically. Preserve the existing stale-review `409` behavior.
- Databricks timeouts, invalid output, or quota exhaustion leave the review open for manual resolution. Existing deterministic matching, ordinary new events, and alerts continue. Turning the integration off must not auto-publish held announcements.
- The documented candidate window is a pilot heuristic, not a guarantee that every duplicate will be detected. Keep a labeled evaluation set with renamed duplicates, true new events, recurring sessions, and room/time changes.

**Exit check:** a renamed duplicate waits for review through a full batch delay and outage, a reviewer links it to the existing event, and no duplicate public event or alert was created while waiting.

## Phase 4: Genie and one useful dashboard

### Student questions in the existing website

1. Create a Genie space over curated public gold tables only. Add table/column descriptions, 6-8 example questions with verified SQL, and a small fixed benchmark set.
2. Instructions define the eight topic slugs, upcoming events, Vancouver time, local start >= 16:00 for "after 4 p.m.", unknown cost failing a free filter, and returning `event_id` for event-search answers. Analytical answers should be labeled separately from event listings.
3. Add `POST /api/ask` to start a Genie conversation, poll with bounded deadlines, and fetch its result. Keep the credential server-side; rate-limit requests and isolate conversation handles between users.
4. Resolve returned event IDs against current SQLite publication state. Render canonical event cards with source links and omit unpublished/cancelled entries. Show data freshness so users can understand batch lag.
5. Return a clear unavailable response when unconfigured, quota-limited, or timed out, while retaining normal event filters. Avoid application logs of question text or private data; Genie conversations have their own provider-side history, so do not promise that questions are never stored anywhere.

The [Genie API guidance](https://docs.databricks.com/aws/en/genie-agents/conversation-api) emphasizes curated metadata, tested example SQL, permissions, and benchmark questions. Validate answer correctness rather than relying on a plausible text response.

### AI/BI dashboard: Campus Club Pulse

- Published events this week by topic, time, and known building, with source coverage and last successful sync.
- The beginner-friendly share, with unknown eligibility shown separately.
- AI-proposed duplicate reviews and reviewer-confirmed duplicates as separate counts.
- Confirmed schedule/venue changes and gaps in free beginner-friendly after-4pm events within the connected sources.

Do not label event revisions or queued notifications as "corrections sent." Add that metric only after exporting anonymous provider-accepted delivery counts, without emails or message payloads.

**Exit check:** tested questions return the expected event IDs and current cards; the dashboard answers one useful organizer question with honest coverage and freshness labels.

## Event history and Delta history

The event audit is `(event_id, revision)` plus old/new values, reason, approver, timestamps, and source evidence. This is what the app and review workflow use to explain a room change.

Delta `DESCRIBE HISTORY` describes table write operations; `VERSION AS OF` queries a table snapshot. Demonstrate these as additional pipeline audit/debugging tools, not as replacements for per-event revisions. [Databricks table history documentation](https://docs.databricks.com/aws/en/tables/history) also describes retention limits.

## Maritime handoff

- The agent submits to the existing authenticated `POST /api/intake` or image-upload endpoint using the configured `SOURCE_INGEST_TOKEN`.
- Start with the existing `src-demo-feed`. Register a separate approved real source, such as `src-maritime-feed`, before using that ID; keep its external listing IDs stable across edits.
- Bronze preserves `source_id`, `external_id`, content hash, detected time, and source URL so the dashboard can distinguish monitored sources from direct submissions.
- A scheduled remote agent needs a reachable HTTPS backend or an explicit development tunnel. Complete one manual intake before scheduling checks. Maritime setup, model usage, and hosting are separate work with costs disclosed before paid actions.

## Files to implement

- **Add:** `app/databricks.py`, `scripts/dbx_worker.py`, an idempotent database migration, `sql/10_bronze.sql`, `sql/20_silver.sql`, `sql/30_gold.sql`, `sql/40_match_judge.sql`, `databricks/notebooks/00_setup.py`, `databricks/notebooks/01_seed_events.py`, `databricks/jobs/pipeline.sql`, `databricks/genie/instructions.md`, and focused Databricks integration tests.
- **Edit:** `app/schema.sql` for queues/jobs; `app/service.py` for atomic enqueueing, conservative review holding, and revision-checked results; review models/routes/UI for suggestions and candidate selection; `app/main.py` for `/api/ask`; and `.env.example` for verified Databricks authentication, the separate Genie credential, `GENIE_SPACE_ID`, `DATABRICKS_TIMEOUT_S`, and `DATABRICKS_MATCH_MODE`.
- **Reuse:** `service.snapshot`, `service.get_event`, `service.public_event`, `matching.decide`, the existing review/delivery outboxes, and `db.load_fixtures`.
- **Keep initially:** `sql/01_tables.sql` and `sql/02_demo_data_and_reconcile.sql` as labeled standalone demos. Retire them only when replacement scripts work and existing references are updated.

## Verification and success criteria

Use focused existing tests plus mocked Databricks tests for the new logic; record workspace checks separately from mocks.

- Atomicity: rollback creates neither a partial local change nor an orphan export; all intake/review paths persist the expected evidence and queue operations.
- Retry safety: crash recovery, repeated exports, out-of-order updates, and repeated result imports produce one current projection and one relevant review.
- Latency: intake/review request handling makes no Databricks network calls and waits for no pipeline run.
- Safety: a semantic candidate remains unpublished while its job is delayed or offline; false/uncertain judgments still require reviewer resolution.
- Concurrency: a changed event revision or a manually resolved review makes a late judgment stale; it cannot alter publication or send an alert.
- Matching quality: report counts of labeled duplicate detections, missed duplicates, and false positives against the existing local matcher. Label the small demo sample honestly.
- History: a confirmed room change updates the same event ID, advances its application revision, and queues exactly the expected correction through existing delivery rules.
- Genie: missing configuration/timeout behavior works, tested questions return expected IDs, and cancelled/private/pending records are excluded from cards and accessible public tables.
- Workspace: run setup, export, transformation, and result import with the actual credentials; verify quota/failure behavior and dashboard freshness.
- End to end: submit fixtures A-C plus a renamed duplicate through FastAPI; observe bronze/gold, complete review, and confirm the public event and alert counts.

## Build order and scope cuts

1. Prove access and a small raw-source -> bronze -> gold export. Measure actual runtime before committing to a completion estimate.
2. Complete one asynchronous semantic review, including duplicate-alert suppression, stale-result handling, and an outage/manual-review demonstration.
3. Add tested Genie questions, then one useful dashboard. Freeze features early enough to rehearse the real integration.

Defer Vector Search, a separate Databricks App, full campus geospatial ingestion, a second AI topic classifier, anonymous engagement instrumentation, and additional datasets. If a map is still worthwhile after the required deliverable works, add it to the existing website using curated gold building coordinates.

## Judge demonstration

1. Show the original announcement and a differently worded duplicate held in review.
2. Show its completed Databricks assessment, evidence, and processing timestamps; have the reviewer link it and show one event with both sources and one announcement.
3. Confirm a room change and show the same event with its explicit old/new application revisions.
4. Ask Genie a tested question such as "free beginner tech events after 4 this week" and open its canonical event cards.
5. Show one organizer insight with the connected-source coverage and last successful sync.

Prepare completed batch results for a 60-90-second presentation when necessary, and clearly label prepared or recorded runs. Do not imply that a 10-minute batch completes immediately during intake. Record which integrations actually ran.
