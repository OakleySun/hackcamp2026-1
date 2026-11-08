"""Create the SQLite database and seed the demo club, sources and test subscribers.
Run from the repo root:  python -m scripts.init_db
"""
from app import config, db


def main() -> None:
    conn = db.connect()
    db.init_db(conn)
    print("Database ready at", config.get("DATABASE_PATH", "data/club_alerts.db"))


if __name__ == "__main__":
    main()
