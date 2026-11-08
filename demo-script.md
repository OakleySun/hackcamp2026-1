# Quad — demo video notes

Read once, then wing it. One continuous screen-share, start to finish, in this order. Each block = what's on screen → what to say while you're there. Sponsors come up when the thing they power is on screen. 3–4 min.

Sponsors: Maritime, Gemini, Lovable, Databricks/Genie, n8n.

---

### 0. Before you hit record

- Backend in demo mode, fresh DB. Frontend on :8080. `quadDemoRefresh` snippet running (README) so pages live-update.
- Fixtures A + C dated upcoming.
- Tabs open behind Quad, in this order: Maritime run log → Databricks Genie space (question pre-tested) → n8n (preview already run).
- Signed in with 2–3 interests. Notifications off.

---

### 1. Quad homepage, just sitting there — the problem (30s)

- UBC, ~60k students, 350+ clubs. AMS capped it — was 445.
- Every club posts somewhere different: Instagram, a Google Calendar nobody follows, Discord, a poster in the Nest.
- Real pain: the room changes and you don't find out. Sign on the door.
- So, Quad. One place, and it stays correct when stuff changes. Let me walk through it.

### 2. Discover page (20s)

- You pick topics at signup. Top section matches them, section below is "something you didn't ask for."
- Click a chip — instant. Same 8 topic labels everywhere, you'll see them again later.
- **Lovable** — this whole frontend was built in it. Scaffolded the React/TanStack app, synced to GitHub, pointed it at our FastAPI backend. It's why we had time for everything else you're about to see.

### 3. Explore page (15s)

- Full list. Filter free / beginner / after 4pm — "is there anything after my last class."
- Save, hide.

### 4. Click into one real event card (40s) — "where did this come from?"

- Point at the source link at the bottom. Nobody typed this in. Clubs get $250 seed funding, there's no data-entry person.
- **Maritime** — flip to the Maritime tab. A worker runs every 15 min, checks 10 source groups: AMS calendars, UBC events page, career workshops, BizTech, club websites from the AMS directory. Pushes to our intake API.
- Show the run log: 78 checked, 0 failures. Sources are independent — one dies, the rest run.
- Instagram: most clubs only post there. Used Maritime's **Computers API** for a persistent Linux desktop with a logged-in Chromium. Reads ~290 club accounts. Fiddly, works.
- Site + API are hosted on Maritime too.
- Flip back to the event. If it came from a calendar, those fields are structured, no AI.
- If it came from an Instagram caption — "FULL STACK PANCAKES thurs 5pm ICCS come hungry" — **Gemini** pulled date/time/venue/organizer/cost/beginner-friendly out of it. Also tags missing topics in the background.
- Point at a "cost unknown" or empty field if there is one: if there's not enough evidence, Gemini skips. Doesn't guess. Unknown beats wrong.

### 5. Map page (15s)

- Pinned to the real building. "ICCS" / "the Nest" aren't locations to a first-year.

### 6. Back to Explore + terminal — the room change (45s) — don't cut this

- "This is the part that makes it not just a scraper."
- Post fixture A → "Intro to Git" appears, Demo Hall 101. Click in. "Say that link goes out to people."
- Post fixture C → same event, new wording, new room. **No second card.** It opened a review. Page still says 101 — an automated match can't change a published event, a human has to okay it.
- Confirm → same URL, now says 204. Scroll to "Confirmed changes" — old room, new room. Back on Explore: one card, "Updated" badge.
- "That's the whole idea."

### 7. Flip to n8n — the alert for that event (20s)

- **n8n** workflow. 8am digest (you're on the 99 deciding if you stay after class). 1-hour reminder with the *current* room — so after what we just did, the reminder says 204, not 101.
- Gmail or ntfy to phone. Receipt table, no double sends.
- Visual workflow = debuggable at 3am.

### 8. Flip to Databricks / Genie — asking questions about all of it (30s)

- Everything we just saw — every post, every revision — exports in the background to **Databricks**. Bronze = raw post, never thrown away. Silver = cleaned + buildings. Gold = current events, activity over time, duplicates caught, gaps.
- **Genie** on top of Gold. Type: "free beginner-friendly tech events after 4 this week." Real answer with organizer, time, building, source link.
- Same 8 topics, same rules as the app: unknown cost ≠ free. "Is it free" is the #1 question on campus.
- Genie only sees public tables. No subscriber data ever goes to Databricks.

### 9. Back to Quad — wrap (15s)

- Maritime watches the sources, Gemini reads the messy ones, our backend keeps one record per event with a human in the loop, n8n gets it to your phone, Databricks/Genie let you ask questions about it, Lovable gave us the time.
- Be honest: Instagram login needs babysitting, alert loop needs more testing. Core thing works.

---

### Extra lines if they fit

- Clubs Days arc: sign up for twelve clubs, twelve newsletters, zero events.
- AMS's own Clubs Days advice: "keep an eye on the AMS Instagram." That's the problem.
- 350 clubs × a couple events a month = thousands a year. Nobody has the real number. (say as estimate)
- "U Build Character."

Running long? Cut the Lovable aside → Instagram detail → n8n receipt detail. Never cut section 6.
