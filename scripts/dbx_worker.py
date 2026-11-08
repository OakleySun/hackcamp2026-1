"""Export queued changes from SQLite to Databricks Bronze, in the background.

    python -m scripts.dbx_worker            # loop forever (every 30 s)
    python -m scripts.dbx_worker --once     # one pass, then exit (good for cron or a demo)
    python -m scripts.dbx_worker --retry-failed --once
    python -m scripts.dbx_worker --backfill --once

Each pass: claim a batch in a short transaction, close it, call Databricks, then record success or
schedule a retry in another short transaction. A crash leaves rows 'claimed' with an expiry, so the
next pass picks them up again. MERGEs are idempotent, so a repeated send never duplicates rows.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone

from app import databricks, db, service

LEASE_SECONDS = 120
MAX_ATTEMPTS = 12
BATCH = 25


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def backfill(conn) -> dict:
    """Queue records from before the export worker was installed."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        announcements = conn.execute(
            "SELECT a.announcement_id FROM source_announcements a WHERE NOT EXISTS ("
            "SELECT 1 FROM dbx_queue q WHERE q.kind='announcement' AND q.aggregate=a.announcement_id)"
        ).fetchall()
        revisions = conn.execute(
            "SELECT r.event_id, r.revision FROM event_revisions r WHERE NOT EXISTS ("
            "SELECT 1 FROM dbx_queue q WHERE q.kind='revision' AND q.aggregate=r.event_id "
            "AND q.version=r.revision)"
        ).fetchall()
        for row in announcements:
            service.enqueue_announcement(conn, row["announcement_id"])
        for row in revisions:
            service.enqueue_revision(conn, row["event_id"], row["revision"])
    return {"announcements": len(announcements), "revisions": len(revisions)}


def claim(conn, limit: int = BATCH) -> list[dict]:
    t = _iso(_now())
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM dbx_queue WHERE (state='pending' AND (next_retry_at IS NULL OR next_retry_at<=?)) "
            "OR (state='claimed' AND claim_expires<=?) ORDER BY created_at, op_key LIMIT ?", (t, t, limit))]
        expires = _iso(_now() + timedelta(seconds=LEASE_SECONDS))
        for r in rows:
            conn.execute("UPDATE dbx_queue SET state='claimed', claim_expires=?, attempts=attempts+1 WHERE op_key=?",
                         (expires, r["op_key"]))
            r["attempts"] += 1
    return rows


def _done(conn, op_key: str) -> None:
    with conn:
        conn.execute("UPDATE dbx_queue SET state='done', done_at=?, claim_expires=NULL, statement_id=NULL, "
                     "last_error=NULL WHERE op_key=? AND state='claimed'", (_iso(_now()), op_key))


def _retry(conn, row: dict, error: str, statement_id: str | None = None) -> None:
    final = row["attempts"] >= MAX_ATTEMPTS
    delay = min(10 * 2 ** (row["attempts"] - 1), 600)
    with conn:
        conn.execute("UPDATE dbx_queue SET state=?, next_retry_at=?, claim_expires=NULL, statement_id=?, "
                     "last_error=? WHERE op_key=? AND state='claimed'",
                     ("failed" if final else "pending", _iso(_now() + timedelta(seconds=delay)),
                      statement_id, error[:500], row["op_key"]))


def run_once(conn, export=databricks.export, statement_state=databricks.statement_state) -> dict:
    summary = {"enabled": databricks.configured(), "claimed": 0, "exported": 0, "retrying": 0}
    if not summary["enabled"]:
        return summary
    rows = claim(conn)
    summary["claimed"] = len(rows)
    for row in rows:
        try:
            if row["statement_id"]:  # a previous send timed out: find out whether it finished
                state = statement_state(row["statement_id"])
                if state == "SUCCEEDED":
                    _done(conn, row["op_key"])
                    summary["exported"] += 1
                    continue
                if state in ("PENDING", "RUNNING"):
                    _retry(conn, row, "previous statement still running", row["statement_id"])
                    summary["retrying"] += 1
                    continue
            export(row["kind"], json.loads(row["payload"]))
            _done(conn, row["op_key"])
            summary["exported"] += 1
        except databricks.StatementPending as exc:
            _retry(conn, row, str(exc), exc.statement_id)
            summary["retrying"] += 1
        except databricks.DatabricksError as exc:
            _retry(conn, row, str(exc))
            summary["retrying"] += 1
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=30)
    parser.add_argument("--backfill", action="store_true", help="queue historical records missing from the export queue")
    parser.add_argument("--retry-failed", action="store_true", help="move failed rows back to pending first")
    args = parser.parse_args()
    conn = db.connect()
    db.init_db(conn)
    if args.backfill:
        print(json.dumps({"backfill": backfill(conn)}), flush=True)
    if args.retry_failed:
        with conn:
            conn.execute("UPDATE dbx_queue SET state='pending', attempts=0, next_retry_at=NULL WHERE state='failed'")
    if not databricks.configured():
        print("Databricks export disabled: set DATABRICKS_HOST, DATABRICKS_WAREHOUSE_ID and DATABRICKS_TOKEN.")
        return
    while True:
        summary = run_once(conn)
        print(json.dumps(summary), flush=True)
        if args.once:
            return
        if summary["claimed"] < BATCH:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
