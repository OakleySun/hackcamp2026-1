# Quad — Devpost demo video script

Rough, casual walkthrough. Target ~3 minutes. Talk like you're showing a friend, not reading slides. Bracketed lines are what's on screen; everything else is roughly what you say.

Sponsors woven in: **Maritime**, **Databricks (+ Genie)**, **Gemini**, **n8n**, **Lovable**. Adjust the list if any of these aren't actual HackCamp sponsors.

---

## 0:00 — Cold open (the problem)

[Screen: a messy grid of club Instagram screenshots / Discord announcements, or just your face]

> "So if you're a UBC student, you know the problem. UBC Vancouver has about 60,000 students and the AMS has 350-plus clubs — and that's *after* they capped it, there were 445 last year. Every single one of those clubs announces events in a different place. Instagram story, a Google Calendar nobody subscribes to, a Discord you're not in, a flyer taped up in the Nest. And then the room changes the morning of and you never find out.
>
> Do the math: 350 clubs, even if each one only runs a couple events a month, that's thousands of events a year — and the honest truth is most students hear about like five of them. Everyone's first year is 'I went to Clubs Days, signed up for twelve mailing lists, and never went to anything.'
>
> We built Quad. One feed for every club event on campus, with a map, and alerts that actually update when stuff changes."

---

## 0:25 — The app (Discover + Explore)

[Screen: open Quad at the Discover page `/`]

> "This is Discover. It's personalized — I picked a couple topics when I signed up, so it's showing me stuff I'd actually go to up top, and then a 'try something new' section underneath so you're not just stuck in your bubble."

[Click a topic chip, feed filters instantly]

> "Every event uses the same eight topic labels across the whole system — the API, the filters here, and the analytics layer we'll get to. That consistency matters later."

[Navigate to `/explore`]

> "Explore is the full list. Filter by topic, free vs paid, beginner-friendly, after 4pm. Save things, hide things."

[Navigate to `/map`]

> "And the map — every event pinned to its actual building on campus, so you can see what's happening near you right now. If you've ever been told 'it's in ICCS' and had no idea that means the computer science building, or had a 10-minute walk from Main Mall to Buchanan in the rain, you get why the pin matters."

> "Quick shoutout: we built the whole frontend in **Lovable**. Honestly it's the reason we had time to do the hard backend stuff. We scaffolded the React / TanStack Start app, the routes, the UI components in Lovable, then synced it to GitHub and wired it to our own FastAPI backend. Frontend was never the bottleneck."

---

## 0:55 — Where the events come from (Maritime)

[Screen: `config/monitored-sources.json` or the Maritime dashboard showing the `club-alerts-monitor` worker + trigger]

> "Okay so the hard part: how do you get events from 350 clubs without anyone manually entering them? Because nobody at the AMS is doing that — clubs get $250 in seed funding and a shared Google Calendar if they're lucky.
>
> That's **Maritime**. We have a scheduled worker on Maritime that runs every 15 minutes and checks ten source groups — AMS calendars, UBC's events page, career workshops, BizTech, individual club websites from the AMS directory — and pushes anything new into our intake API."

[Screen: Maritime run log — "78 announcements checked, 78 unchanged, 0 failures"]

> "It's resilient per source, so if one club's site is down, the other nine groups still get checked. And it's not just cron — we also used Maritime's **Computers API** to provision a persistent Linux desktop with a logged-in Chromium session. That's how we read Instagram captions from a watchlist of ~290 club accounts, which is where most clubs actually post. Maritime is genuinely the backbone here — no Maritime, no data."

[Optional: `maritime/` folder — "the website and API are hosted on Maritime too, with persistent SQLite."]

---

## 1:30 — Making sense of messy posts (Gemini)

[Screen: an Instagram caption or flyer image, then the structured event it became]

> "Calendar feeds are structured, so we parse those directly — no model call needed. But an Instagram caption like 'FULL STACK PANCAKES 🥞 thurs 5pm ICCS come hungry' is not structured.
>
> That's where **Gemini** comes in. It extracts date, time, venue, organizer, cost, beginner-friendliness from captions and uploaded flyers. And there's a background Gemini pass that tags events that are still missing topics — but it's bounded: if the listing doesn't have enough evidence, it skips it instead of guessing. We'd rather have 'unknown' than wrong."

---

## 1:55 — The thing we're proudest of: event identity + live corrections

[Screen: Explore, with a terminal beside it. Follow the README demo.]

> "Here's the part that makes Quad different from a scraper. Every UBC student has lived this: you show up to the room on the poster and there's a sign on the door saying 'MOVED TO ___'. Watch."

[Terminal: POST fixture A → "Intro to Git" card appears in Explore. Open it: **Demo Hall 101**]

> "A club announces a workshop. It shows up. Students get the link."

[Terminal: POST fixture C — the room change. Show `state: review`]

> "Now the club posts again — same event, different wording, new room. Quad recognizes it's the *same event*, not a duplicate, and opens a review instead of publishing a second card. The public page still says 101 until a human confirms."

[Terminal: resolve review → event page flips to **Demo Hall 204**, scroll to **Confirmed changes**]

> "Confirm it — and the page updates in place. Same URL. So the link that already went out to people now shows the correct room, with a visible history of what changed. Back on Explore it's one card with an 'Updated' badge, not two."

---

## 2:30 — Analytics and plain-English questions (Databricks + Genie)

[Screen: Databricks — Bronze tables, then the pipeline notebook, then Genie]

> "Every announcement and every event revision also gets exported in the background to **Databricks**. Bronze is the raw evidence — we never throw away the original post. Silver normalizes it, joins buildings, and Gold is what you'd actually query: current events, campus activity over time, duplicates we caught, and gaps — like which parts of campus or which topics have nothing going on."

[Screen: Genie space "UBC Club Events" — type a question]

> "And then **Genie** sits on top of the Gold tables. So a student can just ask —"

[Type: "free beginner-friendly tech events after 4 this week"]

> "— and get a real answer, with the organizer, time, building, and a link back to the source. 'Free' matters a lot here — the number one thing UBC students ask about any event is 'is there free food', so we're strict: unknown cost is *not* free. Same eight topic labels as the app. Subscriber data never touches Databricks; Genie only sees the public gold tables."

---

## 2:55 — Alerts (n8n)

[Screen: n8n workflow `quad-campus-notifications`, preview output]

> "Last piece: actually telling people. We built the notification layer in **n8n**. A morning digest at 8am Vancouver time — right when you're on the 99 B-Line or the R4 trying to decide if today's worth staying on campus past your last class — with today's events matching your topics, and a one-hour reminder with the *current* room — so if that room change we just did happened, the reminder has the right one. Delivery goes out via Gmail or ntfy to your phone, with a receipt ledger so nobody gets double-sent. n8n let us ship this as a visual workflow we could actually debug at 3am."

---

## 3:10 — Close

[Screen: back to the Quad map or Discover]

> "So that's Quad. Maritime watches the sources, Gemini reads the messy ones, our backend keeps one truthful record per event, Databricks and Genie make it queryable, n8n gets it to your phone, and Lovable let us build the face of it fast.
>
> 60,000 students, 350 clubs, one feed — and the room number is actually right. Thanks."

---

## UBC fun facts / lines to sprinkle in

Pulled these so the script sounds like it's actually from UBC. Sourced ones are safe to say on camera; the rest are vibes — use them as throwaway lines, not stats.

**Sourced (AMS / UBC PAIR, Nov 2026):**
- The AMS has **350+ clubs**. Council capped it at 350 in June 2025 — there were **445** before that, and they said 350 is "where we can provide support, there's enough space and there's enough funding." Great line for "even the AMS can't keep up."
- New clubs now get **$250 seed funding**, down from $500. Clubs are running on nothing, so free tooling for discovery actually matters to them.
- **~60,000 students** on the Vancouver campus (60,944 headcount in 2024/25); ~71,000 across both campuses.
- **AMS Clubs Days** runs every January inside the Nest (Jan 26–30 in 2026) — "different clubs booth on different days, keep an eye on the AMS Instagram." i.e. even the official discovery event tells you to go check Instagram.
- The AMS literally tells students: "there's probably a club for that."

**Estimate (say it as an estimate):**
- 350 clubs × ~2 events/month × 8 months ≈ **5,000+ club events a year**. Even at one event a month it's over 3,000. Nobody has the real number because nobody's tracking it — which is kind of the point.

**Student-isms (unsourced, use casually):**
- "Is there free food?" is the first question about any event.
- "Where's ICCS?" — half of campus can't find the CS building. Also: "DMP", "ESB", "Buch" — every building has a nickname and the poster uses the official one.
- "It's in the Nest" is not a location. The Nest has five floors.
- The walk from Main Mall to the far end of campus in the rain, during a room change, is the villain of this story.
- First year arc: sign up for twelve clubs at Clubs Days → get twelve newsletters → go to zero events.
- "U Build Character" — the campus joke about UBC. (optional, if it lands)

---

## Shot list / prep checklist

- [ ] Backend running in demo mode on a fresh DB (`DATABASE_PATH=data/quad-demo-*.db`), frontend on :8080 pointed at it
- [ ] Run the `quadDemoRefresh` console snippet so the page updates live (see README)
- [ ] Fixtures A and C dated to an upcoming date so they show on Explore
- [ ] Maritime dashboard tab open on the worker run log (the "78 checked, 0 failures" line is a good visual)
- [ ] Databricks tab: one Gold table preview + Genie space ready with a pre-tested question
- [ ] n8n tab: workflow open, "Preview both alerts" already run so the digest output is visible
- [ ] Have `monitored-sources.json` open for the "ten source groups" beat
- [ ] Account signed in with 2–3 interests so Discover looks personalized
- [ ] Mute notifications, hide bookmarks bar, 1080p

## Timing notes

If you're over 3 min, cut in this order: Lovable aside (0:55), the Instagram/Computers API detail, the n8n ledger detail. Don't cut the room-change demo — it's the whole pitch.
