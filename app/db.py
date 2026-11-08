import json
import pathlib
import sqlite3
from datetime import datetime, timezone

from . import config

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = pathlib.Path(__file__).with_name("schema.sql")
FIXTURES = ROOT / "fixtures" / "fixtures.json"


def connect(path: str | None = None) -> sqlite3.Connection:
    path = path or config.get("DATABASE_PATH", "data/club_alerts.db")
    if path != ":memory:":
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def load_fixtures() -> dict:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def init_db(conn: sqlite3.Connection, seed: bool = True) -> None:
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    if seed and config.get("APP_MODE", "demo") == "demo":
        seed_reference_data(conn)


def seed_reference_data(conn: sqlite3.Connection) -> None:
    fx = load_fixtures()
    club = fx["club"]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO clubs (club_id, display_name, aliases) VALUES (?,?,?)",
            (club["club_id"], club["display_name"], json.dumps(club["aliases"])),
        )
        for s in fx["sources"]:
            conn.execute(
                "INSERT OR IGNORE INTO sources (source_id, club_id, kind) VALUES (?,?,?)",
                (s["source_id"], s["club_id"], s["kind"]),
            )
        for sub in fx["subscribers"]:
            conn.execute(
                """INSERT OR IGNORE INTO subscriptions
                   (subscriber_id, email, topics, want_free, want_beginner, after_4pm, verified_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (sub["subscriber_id"], sub["email"], json.dumps(sub["topics"]),
                 int(sub["want_free"]), int(sub["want_beginner"]), int(sub["after_4pm"]), now),
            )


def reset_db(conn: sqlite3.Connection) -> None:
    """Demo only: wipe all tables and re-seed fixtures."""
    tables = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    conn.execute("PRAGMA foreign_keys = OFF")
    for t in tables:
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
