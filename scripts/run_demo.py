"""Run fixtures through the service so the feed has data.
  python -m scripts.run_demo        -> fixture A only (seeded feed)
  python -m scripts.run_demo all    -> A, B (mirror), C (room change, goes to review), D (next week)
"""
import sys

from app import db, service


def main() -> None:
    conn = db.connect()
    db.init_db(conn)
    fx = db.load_fixtures()
    keys = ["A", "B", "C", "D"] if "all" in sys.argv[1:] else ["A"]
    for k in keys:
        a = fx["announcements"][k]
        out = service.intake(conn, a["source_id"], a["external_id"], a["caption"], a["source_url"])
        print(k, out, "| expected:", a["expected"])


if __name__ == "__main__":
    main()
