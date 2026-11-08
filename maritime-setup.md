# Maritime with real UBC and AMS events

The worker checks six public sources: CSSS affiliates, AMS club listings, AMS campus events, CSSS's website calendar, Launch Pad's public calendar, and UBC Events RSS. Source definitions live in [config/monitored-sources.json](config/monitored-sources.json). See [source coverage](source-coverage.md) for current counts and Instagram limitations.

## Verified connection

On 2026-11-08 UTC, the existing `club-alerts-monitor` custom worker deployed successfully with all six sources. Deployment `2895f37f-03dd-4790-8a39-d3381365fcf4` completed at 06:39:37 UTC. A manual remote check completed at 06:40:42 UTC: all six sources succeeded, with 78 announcements checked, 78 unchanged and zero failures. The database contains 46 published events, 32 open reviews and zero subscribers. The import uses explicit source fields without Gemini.

The original CSSS-only worker had already completed a platform-scheduled check at 06:08:09 UTC. The multi-source worker retains that same enabled schedule; the six-source verification above was a manual remote check.

The enabled trigger uses `8,23,38,53 * * * *` with prompt `check`, so it runs every 15 minutes. It is already registered: do not create a second trigger when following the examples below. Agent ID: `64d4de41-90f6-4bf3-8a1f-56e42e18d7d0`; trigger ID: `e3b2123f-93f0-4564-8e8e-8c191c10372e`.

The remote backend URL is `http://127-0-0-1-8000.club-alerts-local.private:20001`. The local backend and `club-alerts-local` connector were left running. Keep the laptop awake and online. After a reboot, start the backend and connector again with the commands below; moving the backend to persistent hosting is a separate deployment. Account usage reported $0 in model calls after the scheduled run. No AI credit purchase or plan change was made.

## Local backend

Install `requirements.txt`, set `APP_MODE=production` in the ignored `.env`, and run:

```powershell
.\.venv\Scripts\python.exe -m scripts.setup_sources
.\.venv\Scripts\python.exe -m uvicorn app.main:app
```

The registration command is idempotent. It registers the six sources and verified organizers without resetting existing data. It creates no sample events or subscribers. Shared sources are not attributed entirely to CSSS or AMS.

Set these non-secret values in `.env`:

```dotenv
APP_MODE=production
APP_BASE_URL=http://127.0.0.1:8000
MARITIME_SOURCES_FILE=config/monitored-sources.json
MARITIME_SOURCE_ID=src-csss-affiliates
MARITIME_FEED_FORMAT=ical
MARITIME_LOOKAHEAD_DAYS=60
MARITIME_FEED_URL=https://calendar.google.com/calendar/ical/1e1ce102f2951b154df282dc66ea69722b37b41a8956d88361befe9ceb9e8080%40group.calendar.google.com/public/basic.ics
```

Keep the generated `SOURCE_INGEST_TOKEN` in `.env`. In another terminal run:

```powershell
.\.venv\Scripts\python.exe -m scripts.check_sources
```

When `MARITIME_SOURCES_FILE` is set, its entries override the legacy single-feed settings. On the remote worker use `/app/config/monitored-sources.json`. Results include one outcome per source, including empty calendars and failures; the other sources continue if one fails. UBC RSS records remain in review because the feed omits event dates and organizer identity. No publication timestamp is used as an event date.

## Calendar behavior

- The checker downloads at most 2 MB and considers the next 60 days. A feed with more than 50 eligible occurrences fails explicitly; shorten the lookahead before retrying.
- Recurrences use `UID` plus the original `RECURRENCE-ID`. Moving one occurrence or changing its room preserves its identity. Separate weeks have separate IDs. EXDATE and recurrence exceptions are respected.
- Publication dates, times and venues come from iCalendar fields, without a model call. Floating times use `America/Vancouver`; date-only entries keep an unknown time.
- Holds, tentative/cancelled listings, reading/academic breaks, planning meetings, TCF meetings, and explicitly internal/exec/board meetings are excluded.
- Explicit recognized club names in `ORGANIZER` or the event title identify an organizer. An unknown organizer stays in review. For joint titles, the first recognized name is the primary organizer in the current single-organizer schema.
- Price, beginner eligibility, topics and RSVP remain unknown unless supported by a later validated submission. Description links are preserved as source text and are not assumed to be RSVP links.
- Polling timestamps and `LAST-MODIFIED` do not change an event's content hash. Rechecking unchanged data creates no second event. A changed date, time, or venue enters the existing review process.
- Filtering cancelled events does not retract an event already published on an earlier poll. Review such cancellations manually until cancellation reconciliation is implemented. Multi-day end dates are retained in source text; the current event schema cannot represent them separately.

## Maritime activation

Read [Maritime's billing documentation](https://maritime.sh/docs/billing.md) and disclose costs before waking the existing agent, uploading files that may wake it, or enabling a schedule. Never upload `.env` or Gemini credentials with the checker.

Use the deterministic custom worker in `scripts/maritime_monitor.py`, built with `maritime/Dockerfile`. It implements Maritime's `/health` and `/chat` endpoints without an LLM. A `check` message starts the checker in the background and returns immediately; `status` reports the last result. Concurrent messages share the running check. Its result is saved to `/data/club-alerts/last-check.json` across sleep and redeploys.

Create the source archive with `python -m scripts.package_monitor`. The ignored `.maritime/custom-monitor.zip` contains only the Dockerfile, monitor dependencies, four Python modules and the public source manifest. The Dockerfile sits at the archive root. Upload with `maritime agents upload-source .maritime/custom-monitor.zip --json`, then redeploy the existing custom agent using the returned `s3Key` as `uploadS3Key` with deployment `source: "zip"`. Do not deploy the whole checkout or upload `.env` or the database.

The existing `club-alerts-monitor` was initially an OpenClaw agent. Waking that template failed with HTTP 402 because its model-proxy balance was zero. Hosting plans, including Scale's $500/month credit, contain no AI credit. The replacement is a real custom Python worker; it does not need a model key, prepaid AI credit or the unused `OPENAI_API_KEY`/`OPENAI_BASE_URL` proxy settings. Preserve unrelated agent settings when redeploying.

The agent needs the feed settings above and the same `SOURCE_INGEST_TOKEN` as FastAPI, saved as an agent secret. Its `APP_BASE_URL` must reach FastAPI. A laptop's loopback address is unavailable from the agent. Use a persistent HTTPS backend, or an explicitly configured Maritime private-network connector while the laptop and backend stay running. Private-network access itself has no additional fee; agent hosting and any model-driven trigger still follow the account's pricing.

For the private connector, start `maritime connect --name club-alerts-local --allow 127.0.0.1:8000` and grant the existing agent access to its returned resource. Set the remote `APP_BASE_URL` to `http://<returned-host>.private:<returned-port>` and `MARITIME_PRIVATE_BACKEND_HOST` to that exact hostname (no scheme/port). Only that explicitly selected `.private` backend may use HTTP; public feeds and flyer downloads still require HTTPS. Keep the local `APP_BASE_URL` on loopback. This connection has not been proven from the remote agent until a remote check succeeds.

For a new installation only, enable a platform cron trigger after a successful manual remote check. The current installation already has its trigger:

```powershell
maritime chat --agent club-alerts-monitor check
maritime chat --agent club-alerts-monitor status
maritime triggers create club-alerts-monitor --type cron --cron "*/15 * * * *" --prompt "check"
maritime triggers list club-alerts-monitor
```

This custom handler executes Python directly, so scheduled checks make no model calls. The worker returns an empty `/schedules` list because these explicit platform triggers own the schedule. Do not add an in-process timer that stops firing while the VM sleeps.

Pass the target with `chat --agent`: this CLI version can include a positional agent name in the delivered message. The handler accepts the exact commands `check`, `check calendar` and `status`.

At the published agent-box rates, the existing 8 GB memory and 100 GB disk allocation is about $11.60/month ($4 memory and $7.60 for 95 GB beyond the included 5 GB), charged against hosting credit. Confirm the account's billing rules and remaining credit before making future resource changes.

n8n verification and delivery email workflows remain a separate integration. Databricks is not required for this source import.

## Instagram browser preparation

See [Instagram browser setup](instagram-browser-setup.md) for the prepared Linux browser and disclosed costs. The original agent's built-in desktop switch returned HTTP 402 `seat_limit` despite the active Scale usage plan. The owner then selected a separate persistent Linux computer, `club-alerts-instagram`. Owner login and CSSS post caption access are verified, and the login survived a sleep/wake cycle. The browser was left asleep with its persistent profile retained. This browser is billed at $0.12/hour awake plus sleeping disk; no subscription upgrade or model call was made. Scheduled Instagram intake is not implemented and remains disabled; no Instagram posts were imported during verification. Do not upgrade the subscription to work around the original agent's conflicting entitlement result.
