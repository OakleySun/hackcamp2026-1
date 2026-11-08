"""Register the public-source manifest without resetting existing events or subscribers."""

import json
from pathlib import Path

from app import db
from scripts.setup_csss import register_csss

MANIFEST = Path(__file__).resolve().parent.parent / "config" / "monitored-sources.json"


def register_sources(conn, manifest=None):
    manifest = manifest or json.loads(MANIFEST.read_text(encoding="utf-8"))
    register_csss(conn)
    # Validate all existing configurations before making additions.
    for source in manifest["sources"]:
        existing = conn.execute("SELECT kind, club_id, url FROM sources WHERE source_id=?",
                                (source["source_id"],)).fetchone()
        if existing and tuple(existing) != (source["kind"], source.get("club_id"), source["url"]):
            raise ValueError(f"Existing configuration differs for {source['source_id']}")
    with conn:
        clubs = list(manifest["clubs"])
        directory = MANIFEST.with_name("club-directory.json")
        if directory.exists():
            clubs.extend({"club_id": c["club_id"], "display_name": c["name"], "aliases": []}
                         for c in json.loads(directory.read_text(encoding="utf-8"))["clubs"])
        for club in clubs:
            conn.execute("INSERT INTO clubs (club_id, display_name, aliases) VALUES (?,?,?) "
                         "ON CONFLICT(club_id) DO NOTHING",
                         (club["club_id"], club["display_name"], json.dumps(club["aliases"])))
        for source in manifest["sources"]:
            conn.execute("INSERT INTO sources (source_id, club_id, kind, url) VALUES (?,?,?,?) "
                         "ON CONFLICT(source_id) DO NOTHING",
                         (source["source_id"], source.get("club_id"), source["kind"], source["url"]))


def main():
    conn = db.connect()
    try:
        register_sources(conn)
    finally:
        conn.close()
    print("Registered public sources. Existing events and subscribers preserved.")


if __name__ == "__main__":
    main()
