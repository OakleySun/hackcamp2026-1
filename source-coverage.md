# Connected event sources

The checker uses the sources in [monitored-sources.json](config/monitored-sources.json). Public calendars and websites use no model or paid scraping API. Calendars cover the next 60 days; BizTech covers 180 days. RSS and unstructured announcements go to review without guessed dates.

## Original six-source import, November 8 at 06:40 UTC

| Source | Checked | Published events | Reviews | Status |
| --- | ---: | ---: | ---: | --- |
| [CSSS affiliate calendar](https://ubccsss.org/about/affiliates/) | 16 | 11 | 5 | Automatic |
| [AMS Club Events](https://amsclubs.ca/all-events/) | 33 | 24 | 9 | Automatic; paginated club listings |
| [AMS campus calendar](https://www.ams.ubc.ca/events/) | 11 | 11 | 0 | Automatic; public Events Calendar API |
| [CSSS website calendar](https://ubccsss.org/events/index.ics) | 0 | 0 | 0 | Connected; no upcoming eligible entries |
| [Launch Pad calendar](https://luma.com/launchpadubc) | 0 | 0 | 0 | Connected; no upcoming entries |
| [UBC Events RSS](https://events.ubc.ca/events/feed/) | 18 | 0 | 18 | Review only; no event date or organizer fields |
| **Total** | **78** | **46** | **32** | **Zero import failures** |

A second local check found all 78 announcements unchanged and created no additional records. The deployed Maritime worker independently checked all six sources at 06:40:42 UTC with the same 78 unchanged announcements and zero failures. Its existing 15-minute schedule remains enabled. Thirteen focused tests passed, covering pagination, duplicate/correction handling, review routing, failure isolation, and the worker contract.

There are no sample events or subscribers. These are the records exposed by the connected sources, not complete coverage of UBC clubs. The AMS campus calendar also includes AMS and Gallery events, not just student clubs.

Nine AMS club listings name an organizer that has not been verified (the listing's club name and sub-site appear inconsistent). They stay in review. Unknown organizers and missing dates are never filled from guesses. UBC RSS publication timestamps are not event dates; clinical UBC CPD entries are excluded from this student-events pilot. The broader UBC REST/calendar endpoints currently return 403, so this integration uses only the accessible public RSS feed.

## Instagram

The [Instagram watchlist](config/instagram-watchlist.json) now contains 294 unique profile URLs: links found for 283 directory clubs, plus the earlier watchlist. Links are taken from each club's AMS page or its linked website/link hub; missing accounts are not guessed. Multiple clubs sharing one profile remain ambiguous for intake.

Public profiles can expose bios and post previews. Initial signed-out CSSS, WiCS and nwPlus post clicks requested sign-in. After owner login, CSSS's "Full Stack Pancakes" post caption was successfully read in the persistent browser. WiCS and nwPlus captions have not yet been verified. WiCS showed a November 5 video and October 28 photo; those are posting dates, not verified event dates. nwPlus's public bio lists HackCamp for November 7–8, 2026 and Learn Week for November 2–6; it does not establish exact event times. Nothing from these previews or the signed-in verification was auto-published.

The deterministic [Instagram reader](scripts/instagram_reader.py) uses the owner's existing Linux browser and local profile. It reads post captions and image alt text, without exporting cookies or invoking Gemini. Every captured post enters review with an unknown event date. Posting timestamps and alt-text dates are never treated as event dates. Private/unavailable profiles are recorded; login challenges and rate limits stop the run with a 24-hour cooldown. No scraper subscription, residential IP or AI credits were purchased.

A [persistent Linux browser](instagram-browser-setup.md) has an earlier verified login that survived sleep/wake. Restarting Chromium for its automation interface reached a login screen, so owner sign-in is pending in the private desktop. The separate twice-daily trigger is prepared but disabled until this reader is verified. See [expanded monitoring setup](club-monitoring.md) for activation status and costs.

## Expanded directory and event sources

All 36 AMS directory pages were traversed and all 317 unique club pages attempted. Of those pages, 316 were readable; Wargamers of UBC returned HTTP 403 on both attempts. The [club inventory](config/club-directory.json) records every club, the provenance of its links, and website check outcomes. Seventy-four clubs list external websites (78 URLs); each was attempted, along with up to two linked event/calendar pages. Missing websites and Instagram links remain visible in the inventory.

| Source | Result of local import |
| --- | --- |
| [UBC Events homepage](https://events.ubc.ca/) | 25 linked announcements sent to review; event-detail pages and full calendar endpoints currently return 403 |
| [UBC career events/workshops](https://students.ubc.ca/career/events-workshops/) | Connected and retried by the checker; currently blocked/unreadable, no events invented |
| [BizTech](https://www.ubcbiztech.com/events) | Four upcoming events imported over 180 days; explicit starting dates retained, times and venues unknown |
| All linked club websites | Daily rotation, ten clubs per 15-minute check; structured Event data is parsed, other dated event text enters review |
| Linked club Instagram accounts | Reader and bounded schedule prepared; owner sign-in verification pending |

After the local expanded import, the database held 50 published events, 57 open reviews and zero subscribers. The expanded worker deployment is `401d6c4e-ed58-4201-9134-3dc260634098`. These counts are a point-in-time result, not a claim of complete campus coverage.

## Operation and limits

See [Maritime setup](maritime-setup.md) for the existing worker and private laptop connection. The source checker isolates failures: one blocked or changed site does not stop the others. The worker reports results for each source.

Rechecks preserve source identities and send conflicting room/date/time changes to review. This importer does not automatically retract events removed or cancelled after an earlier import. HTML adapters can need maintenance when their publishers change markup. Empty feeds are shown as successful checks with zero records, not as import failures.

The backend must stay running and the laptop must remain awake and connected until it moves to persistent hosting. Email delivery and the student-facing frontend remain separate setup work.
