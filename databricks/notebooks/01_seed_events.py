# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Seed demo events (fictional, labelled)
# MAGIC
# MAGIC Fills bronze with ~80 **fictional** UBC club events over the next 2 weeks so the pipeline, Genie and the
# MAGIC dashboard have realistic data before real posts arrive. All demo IDs start with `demo-` and all clubs are
# MAGIC named "Demo …". Re-running replaces the demo rows only; real rows from the backend are never touched.
# MAGIC
# MAGIC The data is deliberately messy, like real club posts:
# MAGIC * venues written many ways ("the Nest 2nd floor", "big Engineering building", "Sauder atrium")
# MAGIC * **near-duplicates**: the same event re-posted by another source with a different title
# MAGIC * **same-day different sessions** that must NOT be merged
# MAGIC * **room changes** (revision 2) and posts found by the **Maritime agent**

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.text("prefix", "club_alerts")
CATALOG, PREFIX = dbutils.widgets.get("catalog"), dbutils.widgets.get("prefix")
BRONZE, SILVER = f"{CATALOG}.{PREFIX}_bronze", f"{CATALOG}.{PREFIX}_silver"

# COMMAND ----------

import json, random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

rng = random.Random(2026)
VAN = ZoneInfo("America/Vancouver")
today = datetime.now(VAN).date()

CLUBS = {
    "demo-coding-club":     ("Demo Coding Club", "tech"),
    "demo-robotics":        ("Demo Robotics Society", "tech"),
    "demo-consulting":      ("Demo Consulting Club", "career"),
    "demo-math-circle":     ("Demo Math Circle", "academic"),
    "demo-watercolour":     ("Demo Watercolour Collective", "arts"),
    "demo-film-society":    ("Demo Film Society", "arts"),
    "demo-climbing":        ("Demo Climbing Club", "sports"),
    "demo-volleyball":      ("Demo Volleyball Club", "sports"),
    "demo-global-cultures": ("Demo Global Cultures Club", "culture"),
    "demo-board-games":     ("Demo Board Games Society", "social"),
    "demo-mindfulness":     ("Demo Mindfulness Club", "wellness"),
}
TEMPLATES = {
    "demo-coding-club": [("Intro to Git", "Learn version control from scratch. Laptops recommended.", ["tech"]),
                         ("Hack Night", "Bring a project or join a team. Snacks provided.", ["tech", "social"]),
                         ("Python for Absolute Beginners", "No experience needed.", ["tech", "academic"])],
    "demo-robotics": [("Arduino Basics Workshop", "Build a blinking LED circuit.", ["tech"]),
                      ("Robot Build Sprint", "Team build session for competition bots.", ["tech"])],
    "demo-consulting": [("Resume Clinic", "Get one-on-one feedback on your resume.", ["career"]),
                        ("Case Interview 101", "Walkthrough of a consulting case.", ["career", "academic"])],
    "demo-math-circle": [("Problem Solving Night", "Puzzles and competition problems.", ["academic"]),
                         ("Putnam Prep", "Practice session for the Putnam exam.", ["academic"])],
    "demo-watercolour": [("Watercolour Night", "All materials provided. Total beginners welcome.", ["arts"]),
                         ("Plein Air Sketching", "Sketch outdoors around campus.", ["arts"])],
    "demo-film-society": [("Movie Night: Studio Ghibli", "Free popcorn.", ["arts", "social"]),
                          ("Short Film Workshop", "Shoot a one-minute film on your phone.", ["arts"])],
    "demo-climbing": [("Bouldering 101", "Shoes provided. No experience needed.", ["sports"]),
                      ("Climbing Social", "Climb and hang out.", ["sports", "social"])],
    "demo-volleyball": [("Rec Volleyball Drop-in", "All levels.", ["sports"]),
                        ("Volleyball Skills Clinic", "Fundamentals for new players.", ["sports"])],
    "demo-global-cultures": [("Lunar New Year Planning Mixer", "Help plan the festival.", ["culture", "social"]),
                             ("World Food Potluck", "Bring a dish from home.", ["culture", "social"])],
    "demo-board-games": [("Board Game Night", "Hundreds of games, all welcome.", ["social"]),
                         ("Catan Tournament", "Prizes for top three.", ["social"])],
    "demo-mindfulness": [("Guided Meditation", "30 minutes, cushions provided.", ["wellness"]),
                         ("Exam Stress Workshop", "Practical tools for exam season.", ["wellness", "academic"])],
}
# Venue strings written the messy ways students actually write them.
VENUES = ["AMS Student Nest room 2306", "the Nest 2nd floor", "Nest Great Hall", "ICICS X-wing lab 005",
          "ICCS 246", "Dempster 110", "the big Engineering building, room 1202", "Kaiser 2020",
          "Sauder atrium", "Henry Angus 098", "IKB 3rd floor", "Irving K. Barber room 261", "Buchanan A101",
          "Buch D218", "Hebb 100", "Hennings 200", "Chem B250", "Biology building 2000", "ESB 1012",
          "LSC 1001", "Woodward IRC 2", "CIRS atrium", "Swing Space 121", "Orchard Commons 3004",
          "SRC multipurpose room", "War Memorial Gym", "Mem Gym court 2", "Chan Centre lobby",
          "Life Building 2201", "Koerner Library lower level", "Forestry building atrium",
          "Somewhere on Main Mall", None]
PARAPHRASE = {"Intro to Git": "Git Workshop for Beginners", "Resume Clinic": "Get Your Resume Reviewed!",
              "Watercolour Night": "Paint & Chill: Watercolour Evening", "Bouldering 101": "Beginner Climbing Session",
              "Board Game Night": "Games Night @ the Nest", "Hack Night": "Weekly Hack Session",
              "Guided Meditation": "Drop-in Meditation Break"}
TIMES = ["12:00", "13:00", "15:30", "16:00", "17:00", "17:30", "18:00", "18:30", "19:00"]

# COMMAND ----------

events, announcements, revisions = [], [], []
n = 0

def add_event(club_id, title, desc, topics, day, start, venue, cost, beginner, source="src-direct-form", rev2_venue=None):
    global n
    n += 1
    eid = f"demo-evt-{n:03d}"
    end = (datetime.strptime(start, "%H:%M") + timedelta(minutes=90)).strftime("%H:%M")
    snap = {"title": title, "description": desc, "local_date": day.isoformat(), "local_start": start,
            "local_end": end, "venue": venue, "cost_status": cost,
            "beginner_friendly": None if beginner is None else int(beginner), "topics": topics,
            "rsvp_url": f"https://example.org/demo/{eid}"}
    created = datetime.combine(day - timedelta(days=rng.randint(2, 6)), datetime.min.time())
    revisions.append((eid, 1, club_id, json.dumps(snap), "{}", "created", created))
    caption = f"{title}! {day.strftime('%b %d')} at {start}, {venue or 'location TBA'}. {desc}"
    announcements.append((f"demo-ann-{n:03d}", source, f"post-{n:03d}", f"https://example.org/demo/post-{n:03d}",
                          created, "linked", caption, json.dumps(snap), eid))
    if rev2_venue:
        new = dict(snap, venue=rev2_venue)
        revisions.append((eid, 2, club_id, json.dumps(new), json.dumps({"venue": {"old": venue, "new": rev2_venue}}),
                          "review confirm", created + timedelta(days=1)))
    return eid, snap

for d in range(14):
    day = today + timedelta(days=d)
    for _ in range(rng.randint(4, 7)):
        club = rng.choice(list(CLUBS))
        title, desc, topics = rng.choice(TEMPLATES[club])
        cost = rng.choices(["free", "paid", "unknown"], [0.7, 0.15, 0.15])[0]
        beginner = rng.choices([True, False, None], [0.55, 0.2, 0.25])[0]
        source = rng.choices(["src-direct-form", "src-demo-feed", "src-maritime-feed"], [0.5, 0.2, 0.3])[0]
        rev2 = rng.choice(VENUES[:-2]) if rng.random() < 0.06 else None
        eid, snap = add_event(club, title, desc, topics, day, rng.choice(TIMES), rng.choice(VENUES),
                              cost, beginner, source, rev2)
        # ~10%: the same occurrence re-posted elsewhere with a different title -> AI judge should merge
        if title in PARAPHRASE and rng.random() < 0.35:
            add_event(club, PARAPHRASE[title], desc, topics, day, snap["local_start"],
                      rng.choice(VENUES), cost, beginner, "src-maritime-feed")

# Same day, different sessions -> AI judge should keep them separate
day = today + timedelta(days=2)
add_event("demo-climbing", "Bouldering 101 (Morning Session)", "Shoes provided.", ["sports"], day, "10:00",
          "SRC multipurpose room", "free", True)
add_event("demo-climbing", "Bouldering 101 (Evening Session)", "Shoes provided.", ["sports"], day, "18:00",
          "SRC multipurpose room", "free", True)
print(f"{len(revisions)} revisions, {len(announcements)} announcements, {n} events")

# COMMAND ----------

now = datetime.utcnow()
rev_df = spark.createDataFrame([r + (now,) for r in revisions],
    "event_id STRING, revision INT, club_id STRING, snapshot_json STRING, changed_json STRING, reason STRING, "
    "created_at TIMESTAMP, ingested_at TIMESTAMP")
ann_df = spark.createDataFrame([a + (now,) for a in announcements],
    "announcement_id STRING, source_id STRING, external_id STRING, source_url STRING, detected_at TIMESTAMP, "
    "status STRING, caption STRING, candidate_json STRING, event_id STRING, ingested_at TIMESTAMP")

spark.sql(f"DELETE FROM {BRONZE}.event_revisions WHERE event_id LIKE 'demo-%'")
spark.sql(f"DELETE FROM {BRONZE}.source_announcements WHERE announcement_id LIKE 'demo-%'")
rev_df.write.mode("append").saveAsTable(f"{BRONZE}.event_revisions")
ann_df.write.mode("append").saveAsTable(f"{BRONZE}.source_announcements")

spark.createDataFrame([(k, v[0], v[1]) for k, v in CLUBS.items()], "club_id STRING, display_name STRING, category STRING") \
    .createOrReplaceTempView("demo_clubs")
spark.sql(f"MERGE INTO {SILVER}.clubs t USING demo_clubs s ON t.club_id = s.club_id "
          "WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *")
# The backend's fictional fixture club
spark.sql(f"MERGE INTO {SILVER}.clubs t USING (SELECT 'demo-campus-coding-club' club_id, "
          "'Demo Campus Coding Club' display_name, 'tech' category) s ON t.club_id = s.club_id WHEN NOT MATCHED THEN INSERT *")

display(spark.sql(f"SELECT source_id, count(*) posts FROM {BRONZE}.source_announcements GROUP BY ALL"))
