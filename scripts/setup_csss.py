"""Register the real CSSS affiliate feed and known clubs without sample subscribers."""

import json

from app import db
from scripts.calendar_feed import CLUBS, CSSS_FEED_URL, CSSS_SOURCE_ID


def register_csss(conn) -> None:
    db.init_db(conn, seed=False)
    with conn:
        for club_id, name, aliases in CLUBS:
            conn.execute(
                "INSERT INTO clubs (club_id, display_name, aliases) VALUES (?,?,?) "
                "ON CONFLICT(club_id) DO NOTHING",
                (club_id, name, json.dumps(aliases)),
            )
        # The shared calendar contains several organizers; do not scope it to CSSS alone.
        conn.execute(
            "INSERT INTO sources (source_id, club_id, kind, url) VALUES (?,NULL,'icalendar',?) "
            "ON CONFLICT(source_id) DO NOTHING",
            (CSSS_SOURCE_ID, CSSS_FEED_URL),
        )
        source = conn.execute("SELECT kind, club_id, url FROM sources WHERE source_id=?", (CSSS_SOURCE_ID,)).fetchone()
        if source["kind"] != "icalendar" or source["club_id"] is not None or source["url"] != CSSS_FEED_URL:
            raise ValueError("Existing CSSS source configuration differs; review it before importing")


def main() -> None:
    conn = db.connect()
    try:
        register_csss(conn)
    finally:
        conn.close()
    print(f"Registered {CSSS_SOURCE_ID} and {len(CLUBS)} known clubs. No events or subscribers added.")


if __name__ == "__main__":
    main()
