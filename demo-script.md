# Quad — demo video script (Devpost)

This is a loose script, not lines to memorize. The vibe is "I'm screen-sharing with a friend and showing them what we built this weekend." Pauses, "uh", backtracking — all fine. Don't sell it, just show it and talk about how it works and what was annoying.

Bracketed stuff is what's on screen. Rough target is 3–4 minutes, but if it runs long because you're actually explaining something, that's okay.

Sponsors that come up naturally: Maritime, Databricks / Genie, Gemini, n8n, Lovable. Drop any that aren't actual HackCamp sponsors.

---

## Opening — just talk about the problem for a sec

[Screen: your face, or just the Quad homepage sitting there]

> "Okay so, quick context on what this is. We go to UBC, and the thing that's always bugged us is — there are like 350 clubs. That's after the AMS capped it, it was 445 last year. And every one of them tells you about their events somewhere different. Some club has an Instagram, some club has a Google Calendar that nobody's subscribed to, some are in a Discord you're not in, a lot of it is literally a poster in the Nest.
>
> And the one that really gets you is when the room changes. You saw the post on Monday, you show up Thursday, there's a sign on the door that says 'moved to somewhere else.' Happens constantly.
>
> So we spent the weekend building a thing called Quad that just... pulls all of that into one place, and — this is the part we cared about — actually keeps it right when stuff changes. Let me just show you."

---

## The app itself

[Screen: Discover page `/`]

> "So this is the home page, we call it Discover. When you sign up you pick a few topics you're into, and it uses that. Top section is stuff that matches what you picked, and then there's a section underneath that's basically 'here's something you didn't ask for but might like,' so it's not just an echo chamber of the two things you clicked."

[Click a topic chip]

> "Filtering's all in the browser so it's instant. One thing we did on purpose — there's exactly eight topic labels, and they're the same eight everywhere. Same in the API, same here, same in the analytics stuff I'll show in a bit. That sounds boring but it saved us a lot of pain later."

[Go to `/explore`]

> "Explore is just the full list. You can filter by topic, free or paid, beginner-friendly, after 4pm — which is the actual question, right, 'is there anything after my last class.' You can save stuff, hide stuff."

[Go to `/map`]

> "And then the map. Every event's pinned to the actual building. This matters more than it sounds like — if you've ever gotten a post that says 'ICCS' and had no idea that's the CS building, or 'the Nest' which is five floors... yeah. The pin helps."

> "Oh — the whole frontend, we built in **Lovable**. I want to be honest about that, it's the reason we had time for the backend. We scaffolded the React / TanStack Start app and all the routes and components in Lovable, synced it to GitHub, and then just pointed it at our own FastAPI backend. The frontend was never the thing we were stressed about this weekend, and that's basically why."

---

## Where the events actually come from

[Screen: `config/monitored-sources.json`, or the Maritime dashboard with the worker]

> "So the actual hard part. How do you get events from 350 clubs when nobody's going to type them in? Because nobody is — clubs get like $250 in seed funding from the AMS now, nobody has a person doing data entry.
>
> This is where **Maritime** comes in, and honestly it's doing most of the heavy lifting. We've got a worker on Maritime that wakes up every 15 minutes and goes through ten groups of sources — the AMS calendars, UBC's own events page, career workshops, BizTech, and then a rotation of individual club websites that we pulled out of the AMS club directory. Anything new, it pushes into our intake API."

[Screen: the Maritime run log — "78 announcements checked, 78 unchanged, 0 failures"]

> "That's a real run from this morning. 78 things checked, nothing changed, no failures. Each source is independent, so if one club's website is down the other nine groups still run — we learned that the hard way early on.
>
> And then the Instagram part, which was its own adventure. Most clubs really only post on Instagram. So we used Maritime's **Computers API** to spin up a persistent Linux desktop, logged into Chromium on it once, and now that same browser session reads captions from a watchlist of about 290 club accounts. It survives sleep/wake, we tested that. I'm not going to pretend it wasn't fiddly, but it works, and there's no other way we were getting Instagram data."

[Optional, if time: `maritime/` folder]

> "The site and the API are hosted on Maritime too, with SQLite on a persistent disk. So it's all in one place."

---

## Reading the messy stuff

[Screen: an Instagram caption or flyer, then the structured event it became]

> "So calendar feeds are easy — they're structured, we just parse the fields, no AI involved. But an Instagram caption is like, 'FULL STACK PANCAKES, thurs 5pm, ICCS, come hungry.' That's not a schema.
>
> That's what we use **Gemini** for. It pulls out the date, time, venue, who's running it, whether it costs anything, whether it's beginner-friendly — from captions and from flyer images people upload. And there's a background Gemini pass that goes back and tags events that are missing topics.
>
> The thing we were careful about — if there's not enough in the post to actually tell, it skips it. It doesn't guess. We'd much rather show 'cost unknown' than tell someone something's free and have it not be."

---

## The part we actually care about — same event, new room

[Screen: Explore on one side, terminal on the other. This is the README demo.]

> "Okay, this is the thing that makes it different from just a scraper, so let me actually run it.
>
> Right now the feed's empty. I'm going to pretend to be a club and announce a workshop."

[Terminal: POST fixture A → "Intro to Git" shows up. Click into it: **Demo Hall 101**]

> "There it is. Intro to Git, Demo Hall 101. Say that link goes out to people.
>
> Now the club posts again. Different wording, same event, but the room's changed."

[Terminal: POST fixture C. Show `state: review`]

> "So — it didn't make a second card. It figured out this is the same event, and instead of just overwriting it or duplicating it, it opened a review. The public page still says 101, because we don't let an automated match change a published event on its own. Someone has to okay it."

[Terminal: resolve the review. Event page flips to **Demo Hall 204**. Scroll to **Confirmed changes**]

> "And when I confirm it — same page, same URL, now it says 204. And down here it shows you what changed, old room, new room. So whoever got that original link, it's still the right link. It just has the right room now. Back on Explore it's one card with a little 'Updated' badge on it instead of two cards.
>
> That's really the whole idea. Everything else is in service of that."

---

## Databricks and Genie

[Screen: Databricks — Bronze tables, the pipeline notebook, then Genie]

> "So everything that comes in — every announcement, every revision like the one we just did — also gets exported in the background to **Databricks**. Bronze is the raw stuff, we never throw out the original post. Silver cleans it up and joins in buildings. And Gold is the tables you'd actually want to look at — what's on right now, how busy campus is over time, the duplicates we caught, and gaps, like 'nothing's happening on this side of campus on Tuesdays.'"

[Screen: Genie space, type a question]

> "And then **Genie** sits on top of the Gold tables, so you can just ask it things in English. Like —"

[Type: "free beginner-friendly tech events after 4 this week"]

> "— and it gives you a real answer, with who's running it, when, what building, link to the source. We gave it the same rules as the app — 'free' means we confirmed free, unknown doesn't count, 'after 4' means 4pm Vancouver time. Honestly 'is it free' is the number one question about any event on campus so we were strict about that one.
>
> And Genie only sees the public tables. Nothing about subscribers or emails ever goes to Databricks."

---

## Getting it to your phone

[Screen: n8n workflow, preview output]

> "Last bit is actually telling people, and we did that in **n8n**. Two things: a morning digest at 8am — so you're on the 99 or whatever deciding if it's worth staying on campus after class, and it tells you what's on today in your topics. And a reminder about an hour before an event with the *current* room. So if that room change we just did happened at noon, the 4pm reminder says 204, not 101.
>
> Goes out over Gmail or ntfy to your phone. There's a little receipt table so nobody gets the same message twice. And honestly n8n being visual was the thing — at 3am being able to click through the nodes and see where it broke was a lot nicer than reading logs."

---

## Wrapping up

[Screen: back on the map or Discover]

> "So yeah, that's Quad. Maritime watches all the sources, Gemini reads the messy ones, our backend keeps one record per event and doesn't let anything change it without a human looking, Databricks and Genie let you actually ask questions about it, n8n gets it to your phone, and Lovable meant we could spend our time on all of that instead of CSS.
>
> It's not finished — the Instagram login still needs babysitting and the alert loop needs more end-to-end testing — but the core thing works, and it's the thing we wished existed in first year. Thanks for watching."

---

## UBC facts and lines, if you want them

Sourced ones are fine to say straight. The rest are just things UBC students say — toss them in if they fit, skip them if they feel forced.

**Sourced (AMS / UBC PAIR, Nov 2026):**
- AMS has 350+ clubs. Council capped it at 350 in June 2025, down from 445. Their quote was that 350 is "where we can provide support, there's enough space and there's enough funding."
- New clubs get $250 seed funding now, down from $500.
- About 60,000 students on the Vancouver campus (60,944 in 2024/25). ~71,000 across both campuses.
- AMS Clubs Days is every January in the Nest (Jan 26–30 in 2026). The official advice for finding out which clubs are there which day is "keep an eye on the AMS Instagram." Which is kind of the whole problem.
- The AMS's own tagline for clubs is "there's probably a club for that."

**Estimate — say it as one:**
- 350 clubs, even at a couple events a month, is thousands of events a year. Nobody has the real number because nobody's tracking it.

**Things students say (unsourced, casual):**
- "Is there free food" — first question about anything.
- "Where's ICCS" / "it's in Buch" / "DMP" — every building has a nickname and the poster uses the official one.
- "It's in the Nest" is not a location.
- Clubs Days arc: sign up for twelve clubs, get twelve newsletters, go to zero events.
- "U Build Character," if you want a joke.

---

## Before recording

- [ ] Backend in demo mode on a fresh DB (`DATABASE_PATH=data/quad-demo-*.db`), frontend on :8080 pointed at it
- [ ] Run the `quadDemoRefresh` console snippet from the README so the page updates live
- [ ] Fixtures A and C dated to an upcoming date so they show on Explore
- [ ] Maritime dashboard open on the run log — the "78 checked, 0 failures" line is a good visual
- [ ] Databricks: one Gold table open, Genie space open, question pre-tested
- [ ] n8n: workflow open, "Preview both alerts" already run so the output is sitting there
- [ ] `monitored-sources.json` open for the sources bit
- [ ] Signed in with 2–3 interests so Discover doesn't look empty
- [ ] Notifications off, bookmarks bar hidden

If it runs long, trim in this order: the Lovable aside, the Instagram / Computers API detail, the n8n receipt-table detail. Don't cut the room-change part.
