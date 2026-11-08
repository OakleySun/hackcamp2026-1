# Databricks notebook source
# MAGIC %md
# MAGIC # 00 · Setup: schemas, bronze tables and UBC buildings
# MAGIC
# MAGIC Run once. Creates the medallion schemas for UBC Club Alerts and a reference table of UBC Vancouver buildings
# MAGIC used to place events on the campus map.
# MAGIC
# MAGIC * **Bronze** – raw club posts and every event revision, exactly as the app received them
# MAGIC * **Silver** – cleaned events, AI-resolved venues → buildings, buildings reference
# MAGIC * **Gold** – serving tables for the map app, Genie and the dashboard
# MAGIC
# MAGIC Building coordinates below are approximate building centres. For exact footprints, upload the UBC Geodata
# MAGIC buildings GeoJSON (CC BY 4.0, also used in the Databricks HackCamp workshop) to the `raw` volume and run the
# MAGIC optional cell at the bottom.

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.text("prefix", "club_alerts")
CATALOG = dbutils.widgets.get("catalog")
PREFIX = dbutils.widgets.get("prefix")
BRONZE, SILVER, GOLD = (f"{CATALOG}.{PREFIX}_{x}" for x in ("bronze", "silver", "gold"))

for schema in (BRONZE, SILVER, GOLD):
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {schema}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {BRONZE}.raw")
print("Schemas ready:", BRONZE, SILVER, GOLD)

# COMMAND ----------

# MAGIC %md ## Bronze tables (the backend MERGEs into these; the seed notebook fills them for the demo)

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {BRONZE}.source_announcements (
  announcement_id STRING NOT NULL COMMENT 'One version of one source post',
  source_id       STRING COMMENT 'direct form, demo feed, or src-maritime-feed when found by the Maritime agent',
  external_id     STRING,
  source_url      STRING,
  detected_at     TIMESTAMP,
  status          STRING COMMENT 'pending | linked | review | rejected',
  caption         STRING COMMENT 'Raw caption / flyer text',
  candidate_json  STRING COMMENT 'Fields extracted by Gemini',
  event_id        STRING,
  ingested_at     TIMESTAMP
) COMMENT 'Raw club announcements as received by UBC Club Alerts'
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {BRONZE}.event_revisions (
  event_id      STRING NOT NULL,
  revision      INT NOT NULL,
  club_id       STRING,
  snapshot_json STRING COMMENT 'Public event fields at this revision',
  changed_json  STRING COMMENT 'field -> {{old, new}} for this revision',
  reason        STRING,
  created_at    TIMESTAMP,
  ingested_at   TIMESTAMP
) COMMENT 'Every published version of every event'
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {BRONZE}.engagement_daily (
  day      DATE,
  event_id STRING,
  action   STRING COMMENT 'view | save | rsvp_click | stretch_click | dismiss',
  count    BIGINT
) COMMENT 'Anonymous daily counts only. No profile IDs, no emails.'
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {SILVER}.clubs (
  club_id STRING, display_name STRING, category STRING
) COMMENT 'Clubs known to the pilot (fictional demo clubs are labelled)'
""")

# COMMAND ----------

# MAGIC %md ## UBC buildings reference

# COMMAND ----------

buildings = [
    # code, name, aliases, lat, lon  (approximate centres)
    ("NEST", "AMS Student Nest", ["Nest", "The Nest", "AMS Nest", "Student Nest", "SUB"], 49.2664, -123.2496),
    ("LIFE", "UBC Life Building", ["Life Building", "Old SUB"], 49.2675, -123.2502),
    ("ICCS", "ICICS / Computer Science", ["ICICS", "ICCS"], 49.2612, -123.2489),
    ("DMP", "Hugh Dempster Pavilion", ["Dempster", "DMP"], 49.2613, -123.2481),
    ("KAIS", "Fred Kaiser Building", ["Kaiser", "KAIS"], 49.2620, -123.2496),
    ("MCLD", "MacLeod Building", ["MacLeod", "MCLD", "ECE building"], 49.2618, -123.2491),
    ("CEME", "Civil and Mechanical Engineering", ["CEME", "Civil Mech"], 49.2622, -123.2483),
    ("IKB", "Irving K. Barber Learning Centre", ["IKB", "Irving", "Barber"], 49.2676, -123.2527),
    ("KOER", "Koerner Library", ["Koerner"], 49.2669, -123.2555),
    ("BUCH", "Buchanan Building", ["Buchanan", "BUCH", "Buch"], 49.2690, -123.2546),
    ("HA", "Henry Angus", ["Angus", "Sauder", "HA"], 49.2650, -123.2537),
    ("HEBB", "Hebb Building", ["Hebb"], 49.2662, -123.2517),
    ("HENN", "Hennings Building", ["Hennings", "HENN"], 49.2665, -123.2523),
    ("CHEM", "Chemistry Building", ["Chemistry", "CHEM", "Chem"], 49.2659, -123.2531),
    ("BIOL", "Biological Sciences", ["Biology building", "BIOL", "Bio Sci"], 49.2644, -123.2513),
    ("ESB", "Earth Sciences Building", ["ESB", "Earth Sciences"], 49.2626, -123.2523),
    ("LSC", "Life Sciences Centre", ["LSC", "Life Sciences"], 49.2622, -123.2452),
    ("WOOD", "Woodward IRC", ["Woodward", "WOOD", "IRC"], 49.2645, -123.2475),
    ("CIRS", "CIRS", ["Centre for Interactive Research on Sustainability"], 49.2621, -123.2533),
    ("SWNG", "West Mall Swing Space", ["Swing Space", "SWNG"], 49.2627, -123.2541),
    ("ORCH", "Orchard Commons", ["Orchard", "ORCH"], 49.2603, -123.2509),
    ("SRC", "Student Recreation Centre", ["SRC", "Rec Centre"], 49.2683, -123.2489),
    ("MEMG", "War Memorial Gym", ["War Memorial", "MEMG", "Mem Gym"], 49.2669, -123.2485),
    ("CHAN", "Chan Centre for the Performing Arts", ["Chan Centre", "Chan"], 49.2697, -123.2556),
    ("FSC", "Forest Sciences Centre", ["Forestry", "FSC"], 49.2603, -123.2486),
]
from pyspark.sql import Row
spark.createDataFrame([Row(building_code=c, name=n, aliases=a, lat=la, lon=lo) for c, n, a, la, lo in buildings]) \
    .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{SILVER}.buildings")
spark.sql(f"COMMENT ON TABLE {SILVER}.buildings IS 'UBC Vancouver buildings with approximate centre coordinates'")
display(spark.table(f"{SILVER}.buildings"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Optional: exact centroids from UBC Geodata
# MAGIC Upload the UBC Geodata buildings GeoJSON to `/Volumes/<catalog>/<prefix>_bronze/raw/ubc_buildings.geojson`,
# MAGIC then run this cell. It updates coordinates for codes it can match and keeps the list above as the fallback.

# COMMAND ----------

import json, os
path = f"/Volumes/{CATALOG}/{PREFIX}_bronze/raw/ubc_buildings.geojson"
if os.path.exists(path):
    gj = json.load(open(path))
    rows = []
    for f in gj.get("features", []):
        props, geom = f.get("properties", {}), f.get("geometry") or {}
        code = props.get("BLDG_CODE") or props.get("bldg_code") or props.get("code")
        coords = geom.get("coordinates") or []
        ring = coords[0][0] if geom.get("type") == "MultiPolygon" else (coords[0] if coords else [])
        if code and ring:
            rows.append((code, sum(p[1] for p in ring) / len(ring), sum(p[0] for p in ring) / len(ring)))
    spark.createDataFrame(rows, "code STRING, lat DOUBLE, lon DOUBLE").createOrReplaceTempView("geo")
    spark.sql(f"MERGE INTO {SILVER}.buildings b USING geo g ON b.building_code = g.code "
              "WHEN MATCHED THEN UPDATE SET b.lat = g.lat, b.lon = g.lon")
    print(f"Updated coordinates from {len(rows)} footprints")
else:
    print("No GeoJSON uploaded; using approximate centres.")
