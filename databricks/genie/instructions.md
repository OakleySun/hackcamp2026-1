# Genie space: "UBC Club Events"

Students ask in plain English ("free beginner tech events after 4 this week near the Nest") and Genie answers from the gold tables built by `02_pipeline`.

## 1. Create the space

1. Sidebar → **Genie Agents** → **New**.
2. **Title:** `UBC Club Events`
3. **Description:** `Ask about upcoming UBC club events: topics, times, buildings, cost and beginner-friendliness.`
4. **SQL warehouse:** your Serverless Starter warehouse.
5. **Tables:** add these only, never anything with subscriber data:
   - `workspace.club_alerts_gold.events_current`
   - `workspace.club_alerts_gold.campus_activity`
   - `workspace.club_alerts_gold.opportunity_gaps`
   - `workspace.club_alerts_gold.duplicates_caught`
   - `workspace.club_alerts_gold.pipeline_stats`
   - `workspace.club_alerts_silver.buildings`

## 2. Paste into **Instructions** (General instructions)

```text
You help UBC Vancouver students find club events. Answer from events_current unless the question is about trends, gaps, duplicates or pipeline numbers.

Rules:
- Only show upcoming events (is_upcoming = true) unless the user asks about the past. Sort by local_date, then local_start.
- Always include event_id, title, club_name, local_date, local_start, building_name (or venue if building_name is null), cost_status and beginner_friendly in event results.
- "Free" means cost_status = 'free'. Treat 'unknown' cost as NOT free.
- "Beginner", "beginner-friendly", "no experience" or "newcomer" means beginner_friendly = true. NULL is not beginner-friendly.
- "After class", "evening" or "after 4" means after_4pm = true (local start at or after 16:00 Vancouver time).
- "This week" means local_date between current_date() and current_date() + 6. "Today" means current_date(). "Tomorrow" means current_date() + 1. "Weekend" means the next Saturday and Sunday.
- Topics are an array. Use array_contains(topics, '<slug>'). Valid slugs: tech, career, academic, arts, sports, culture, social, wellness. Map synonyms: coding/programming/CS → tech; jobs/resume/networking → career; study/math/exam → academic; art/painting/film/music → arts; fitness/climbing/volleyball → sports; cultural/international → culture; games/meet people/hang out → social; mental health/meditation/stress → wellness.
- "Near <place>" means events whose building_code matches the place or is the closest buildings by lat/lon. Use silver.buildings to find the place's coordinates, then order events by distance.
- If a location is unclear (location_note = 'Location unclear'), still show the event and say the location is unclear.
- Keep answers short and friendly. Never invent events that are not in the table.
- All clubs whose names start with "Demo" are fictional demo data for HackCamp.
```

## 3. Add **SQL example queries** (Instructions → SQL queries → Add)

**Free beginner tech events after 4 this week**
```sql
SELECT event_id, title, club_name, local_date, local_start, coalesce(building_name, venue) AS location, cost_status, beginner_friendly
FROM workspace.club_alerts_gold.events_current
WHERE is_upcoming AND array_contains(topics, 'tech') AND is_free AND beginner_friendly AND after_4pm
  AND local_date BETWEEN current_date() AND date_add(current_date(), 6)
ORDER BY local_date, local_start;
```

**What's happening near the Nest tonight**
```sql
WITH here AS (SELECT lat, lon FROM workspace.club_alerts_silver.buildings WHERE building_code = 'NEST')
SELECT e.event_id, e.title, e.club_name, e.local_start, e.building_name,
       round(111000 * sqrt(pow(e.lat - here.lat, 2) + pow((e.lon - here.lon) * cos(radians(here.lat)), 2))) AS metres_away
FROM workspace.club_alerts_gold.events_current e CROSS JOIN here
WHERE e.local_date = current_date() AND e.after_4pm AND e.lat IS NOT NULL
ORDER BY metres_away, e.local_start;
```

**Something new to try: free beginner events outside tech**
```sql
SELECT event_id, title, club_name, topics, local_date, local_start, coalesce(building_name, venue) AS location
FROM workspace.club_alerts_gold.events_current
WHERE is_upcoming AND is_free AND beginner_friendly AND NOT array_contains(topics, 'tech')
ORDER BY local_date, local_start
LIMIT 5;
```

**Which topics are hardest for commuters to join**
```sql
SELECT topic, upcoming_events, accessible_events, pct_accessible
FROM workspace.club_alerts_gold.opportunity_gaps
ORDER BY pct_accessible;
```

**Which duplicates did the AI catch**
```sql
SELECT kept_title, merged_title, reason FROM workspace.club_alerts_gold.duplicates_caught ORDER BY judged_at DESC;
```

**Busiest buildings this week**
```sql
SELECT building_name, sum(events) AS events
FROM workspace.club_alerts_gold.campus_activity
WHERE building_name IS NOT NULL
GROUP BY building_name ORDER BY events DESC LIMIT 10;
```

## 4. Add **sample questions** (shown to users)

- Free beginner tech events after 4 this week?
- What's on near the Nest tonight?
- I want to try something new. Any free beginner events that aren't tech?
- Which topics have the fewest free evening events for beginners?
- Which duplicate posts did the AI merge, and why?
- What's happening this weekend?

## 5. Test it

Ask each sample question in the Genie chat. Check that the results only include upcoming events and that "free" excludes unknown cost. If an answer is wrong, click **thumbs down → Fix it** or add another example query for that kind of question.

Then copy the **space ID** from the URL (`.../genie/rooms/<SPACE_ID>`) and put it in the backend `.env` as `GENIE_SPACE_ID`.
