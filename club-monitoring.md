# Directory-wide club monitoring

## Connected sources

The existing `club-alerts-monitor` now has ten public source groups and a separate Instagram group in [monitored-sources.json](config/monitored-sources.json). The existing public trigger remains `8,23,38,53 * * * *` (UTC). Do not create another public trigger.

The public groups include AMS club events, AMS campus events, CSSS calendars, Launch Pad, UBC Events RSS and homepage announcements, UBC career events/workshops, BizTech, and the club website rotation. BizTech uses a 180-day horizon; the other dated calendars retain their 60-day horizon. Career workshops currently return HTTP 403/unreadable content and are reported as blocked, rather than silently treated as an empty calendar.

Deployment `401d6c4e-ed58-4201-9134-3dc260634098` succeeded on November 8, 2026. Public configuration is uploaded to `/data/club-alerts/monitored-sources.json`; the image also contains defaults under `/app/config`. The agent's environment selects the uploaded configuration. Runtime cursors live under `/data/club-alerts`, surviving sleep and redeployment.

## All AMS directory entries

The discovery traversed all 36 directory pages and attempted all 317 unique club pages. The [inventory](config/club-directory.json) contains per-club evidence and outcomes. It found websites for 74 clubs (78 URLs) and Instagram links for 283 clubs. Wargamers' directory page returned 403 twice. Clubs without published website or Instagram links remain in the inventory with empty link lists; no handles are guessed.

The initial discovery attempted each linked website and up to two event/calendar links. Recurring checks rotate through ten clubs on each public trigger, checking each club at most once per 24 hours. A complete rotation takes about eight hours when checks finish normally. Public structured `Event` data supplies explicit dates; unstructured dated event text is retained for review. A successful HTTP response does not guarantee that JavaScript-only event listings were readable.

Refresh the directory and watchlist with `python -m scripts.club_directory`. This makes public HTTP requests locally, without model calls. Re-register sources with `python -m scripts.setup_sources`, package with `python -m scripts.package_monitor`, then upload the code-only archive. Upload the refreshed public manifest and restart the worker when changing its environment. Do not upload `.env`, browser profiles, databases, or screenshots.

## Instagram activation

The [watchlist](config/instagram-watchlist.json) has 294 unique profile URLs, including the earlier watchlist. The existing Linux computer is `club-alerts-instagram` (`1667005f-7f99-4cb5-aaf6-94a4b72c1c05`). Its saved profile is `/home/desk/.config/chromium`. The deterministic [reader](scripts/instagram_reader.py) is installed under `/home/desk/club-alerts` with its own Python environment and `websocket-client` 1.9.2. It connects to Chromium's local-only automation interface and never exports cookies or passwords.

**Current blocker:** the earlier Instagram login survived sleep/wake, but restarting Chromium for automation requested sign-in. The owner has been handed the private desktop for sign-in. No successful automated caption check or Instagram import is claimed yet.

The dedicated Computers-only API key is stored as the worker's `MARITIME_COMPUTERS_KEY` secret. `MARITIME_INSTAGRAM_ENABLED=false` and trigger `fb3cd165-89fe-4987-9d72-2ce232c5db78` is disabled until the reader is verified. No additional key or password needs to be entered into chat.

After the owner signs in and clicks **Done**:

1. Verify the reader against a club profile and confirm captions are returned.
2. Enable `MARITIME_INSTAGRAM_ENABLED` on the existing worker, restart it to apply the environment, and run a bounded manual check.
3. Enable the already-created Instagram trigger: `0 9,21 * * *`, prompt `check instagram` (09:00 and 21:00 UTC). Keep the public trigger unchanged.

The browser run is separate from public-source checks. The custom HTTP worker accepts `check instagram` and `instagram status` in addition to `check` and `status`. It acknowledges immediately and does background work without an LLM. The controller claims each half-day window once, rotates least-recently-checked accounts first, and allows at most 3,300 seconds per window. It sleeps the computer in `finally` unless the owner has taken control. Manual takeover and login time are additional awake time.

Each visit reads a bounded number of visible grid posts, prioritizing posts not seen before and revisiting a prior post for edits. It does not exhaust complete account histories, Stories, or every carousel image. Captions and image alt text enter review with no assumed event date; image-only flyers need manual review or a separately approved model integration. Login requirements and rate limits stop checks and impose a 24-hour cooldown. Private or unavailable profiles are recorded without trying to bypass access controls.

## Disclosed costs

- Existing calendar/website worker: approximately **$11.60/month**, unchanged allocation (8 GB RAM, 100 GB disk).
- Existing Linux browser: **$0.12/hour awake**. Two bounded windows allow under two hours per day, approximately **$7.20/month** at a 30-day upper estimate, plus startup/sleep overhead and any manual takeover time.
- Sleeping browser disk: **$0.08/GB-month**. The API has not exposed its allocated size, so an exact storage total is unavailable.
- These hosting charges draw from the existing **$500/month hosting credit**. Other account workloads also consume that credit; usage beyond it is billed. No upgrade, residential proxy, scraper subscription or AI credit purchase was made.
- The reader and public import make **zero model calls**. Gemini extraction would be a separate cost decision.

Rates: [Maritime billing](https://maritime.sh/docs/billing) and [Linux computers](https://maritime.sh/docs/computers).

## Verification and limits

Nineteen focused tests cover the source adapters, directory pagination/channel boundaries, explicit versus unknown dates, duplicate/review routing, worker behavior, and Instagram window/cooldown/sleep behavior with mocked APIs. The initial expanded local import contained 50 published events, 57 open reviews and zero subscribers. Remote public checks report individual blocked sources instead of stopping the others.

The remote check at 07:48:04 UTC verified 107 unchanged announcements, including all four BizTech events, without duplicate intake. It inspected the next ten directory clubs (297 still due in that day's rotation) and recorded two access failures: UBC Careers HTTP 403 and one club website failure. Module syntax, configuration JSON, unique directory IDs, and `git diff --check` also passed. Automated Instagram caption access remains unverified pending owner sign-in.

The backend and private-network connector still run on the owner's laptop. Keep them running and the laptop awake/online until backend hosting is moved. A website removing or cancelling a previously imported event does not yet retract it automatically. See [source coverage](source-coverage.md) for detailed results.
