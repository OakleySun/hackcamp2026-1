# Databricks notebook source
"""Run after 02_pipeline.sql in the same job and return a bounded public snapshot."""

import json
from datetime import datetime, timezone

stats = spark.table("workspace.club_alerts_gold.pipeline_stats").first().asDict()
events = spark.sql("""
    SELECT event_id, revision, source_url, building_name, location_method
    FROM workspace.club_alerts_gold.events_current
    WHERE is_upcoming AND source_url IS NOT NULL
    ORDER BY updated_at DESC, event_id
    LIMIT 12
""").collect()

dbutils.notebook.exit(json.dumps({
    "refreshed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "metrics": {
        "announcements": stats["posts_received"],
        "upcoming_events": stats["upcoming_events"],
        "event_revisions": stats["confirmed_changes"],
        "venues_placed_by_ai": stats["venues_placed_by_ai"],
        "possible_duplicates": stats["duplicates_caught_by_ai"],
    },
    "events": [row.asDict() for row in events],
}))
