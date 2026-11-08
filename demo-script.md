# Quad — demo video notes

Read once, then wing it. Screen-share and talk like you're showing a friend. 3–4 min.

## 1. The problem (30s, just talk)

- UBC, ~60k students, 350+ clubs (AMS capped it — was 445).
- Every club posts somewhere different: Instagram, a Google Calendar nobody follows, Discord, a poster in the Nest.
- The real pain: the room changes and you don't find out. Sign on the door.
- Quad = everything in one place, and it stays correct when stuff changes.

## 2. Walk through the app (45s)

- **Discover** — you pick topics at signup, top section matches them, section below is "something you didn't ask for."
- Click a chip — instant. Same 8 topic labels everywhere (API, site, Databricks). Boring but saved us.
- **Explore** — full list. Filter free / beginner / after 4pm. Save, hide.
- **Map** — pinned to the real building. "ICCS" / "the Nest" aren't locations to a first-year.
- **Lovable** — built the whole frontend in it. Scaffolded React/TanStack, synced to GitHub, pointed at our FastAPI backend. Reason we had time for the hard stuff.

## 3. Where the events come from — Maritime (45s)

- Nobody's typing these in. Clubs get $250 seed funding, there's no data-entry person.
- **Maritime** worker runs every 15 min, checks 10 source groups: AMS calendars, UBC events page, career workshops, BizTech, club websites from the AMS directory. Pushes to our intake API.
- Show the run log: 78 checked, 0 failures. Sources are independent — one dies, the rest run.
- Instagram: most clubs only post there. Used Maritime's **Computers API** for a persistent Linux desktop with a logged-in Chromium. Reads ~290 club accounts. Fiddly but it works.
- Site + API hosted on Maritime too, SQLite on persistent disk.

## 4. Reading messy posts — Gemini (20s)

- Calendars are structured, no AI needed.
- Instagram captions aren't. "FULL STACK PANCAKES thurs 5pm ICCS come hungry."
- **Gemini** pulls date/time/venue/organizer/cost/beginner-friendly from captions and flyers. Background pass tags missing topics.
- If there's not enough evidence it skips. Doesn't guess. "Unknown" beats wrong.

## 5. THE demo — same event, new room (45s) — don't cut this

Terminal next to Explore. Steps are in the README.

- Feed's empty. Post fixture A → "Intro to Git" appears, Demo Hall 101. "Link goes out."
- Post fixture C → same event, new wording, new room. **No second card.** It opens a review. Public page still says 101 — automated match can't change a published event, human has to okay it.
- Confirm → same URL, now says 204. Scroll to "Confirmed changes" — old room, new room. Back on Explore: one card, "Updated" badge.
- "That's the whole idea. Everything else serves that."

## 6. Databricks + Genie (30s)

- Everything exports in the background to **Databricks**. Bronze = raw post, never thrown away. Silver = cleaned + buildings. Gold = current events, campus activity, duplicates caught, gaps.
- **Genie** on top of Gold. Type: "free beginner-friendly tech events after 4 this week." Real answer with organizer, time, building, source link.
- Same rules as the app: unknown cost ≠ free. "Is it free" is the #1 question on campus.
- Genie only sees public tables. No subscriber data ever goes to Databricks.

## 7. Alerts — n8n (20s)

- **n8n** workflow. 8am digest (you're on the 99, deciding if you stay after class). 1-hour reminder with the *current* room — so after that room change, the reminder says 204.
- Gmail or ntfy to phone. Receipt table so no double sends.
- Visual workflow = debuggable at 3am.

## 8. Wrap (15s)

- Maritime watches sources, Gemini reads the messy ones, backend keeps one record per event with a human in the loop, Databricks/Genie make it askable, n8n gets it to your phone, Lovable gave us the time.
- Be honest: Instagram login needs babysitting, alert loop needs more testing. Core thing works.

---

## Extra lines if they fit

- Clubs Days arc: sign up for twelve clubs, twelve newsletters, zero events.
- AMS's own advice for Clubs Days: "keep an eye on the AMS Instagram." That's the problem.
- 350 clubs × a couple events a month = thousands a year. Nobody has the real number. (say as estimate)
- "U Build Character."

## Before recording

- Backend in demo mode, fresh DB. Frontend on :8080.
- Run the `quadDemoRefresh` console snippet (README) so the page live-updates.
- Fixtures A + C dated upcoming.
- Tabs ready: Maritime run log, Databricks Gold table + Genie (question pre-tested), n8n with preview already run, `monitored-sources.json`.
- Signed in with 2–3 interests.
- Notifications off.

Running long? Cut Lovable aside → Instagram detail → n8n receipt detail. Never cut section 5.
