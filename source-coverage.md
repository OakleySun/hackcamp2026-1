# Connected event sources

The checker uses the public sources in [monitored-sources.json](config/monitored-sources.json). It reads explicit calendar/listing fields without an AI call, login or paid scraping API. Calendars cover the next 60 days; RSS is an announcement review inbox, not a dated event calendar.

## Live import on November 8, 2026 UTC

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

The [Instagram watchlist](config/instagram-watchlist.json) contains 13 official account links: CSSS, WiCS, nwPlus, Anime, Game Dev, WiDS, QueerCoded, ML Research, Quantum, Startups, Launch Pad, Chess and Calligraphy. This is a manual watchlist, not an active post feed.

Public profiles can expose bios and post previews. Initial signed-out CSSS, WiCS and nwPlus post clicks requested sign-in. After owner login, CSSS's "Full Stack Pancakes" post caption was successfully read in the persistent browser. WiCS and nwPlus captions have not yet been verified. WiCS showed a November 5 video and October 28 photo; those are posting dates, not verified event dates. nwPlus's public bio lists HackCamp for November 7–8, 2026 and Learn Week for November 2–6; it does not establish exact event times. Nothing from these previews or the signed-in verification was auto-published.

Reliable Instagram intake needs an organizer-authorized integration or a club forwarding the original post URL, caption and flyer through the existing intake. No Instagram credentials, paid scraper or AI credits were purchased. A flyer submitted to Gemini is a separate model call and would require a cost decision first.

A [persistent Linux browser](instagram-browser-setup.md) has a verified owner login that survived a sleep/wake cycle. It was left asleep with its profile retained. This browser is not yet part of the scheduled source checker; automated Instagram intake remains disabled.

## Operation and limits

See [Maritime setup](maritime-setup.md) for the existing worker and private laptop connection. The source checker isolates failures: one blocked or changed site does not stop the others. The worker reports results for each source.

Rechecks preserve source identities and send conflicting room/date/time changes to review. This importer does not automatically retract events removed or cancelled after an earlier import. HTML adapters can need maintenance when their publishers change markup. Empty feeds are shown as successful checks with zero records, not as import failures.

The backend must stay running and the laptop must remain awake and connected until it moves to persistent hosting. Email delivery and the student-facing frontend remain separate setup work.
