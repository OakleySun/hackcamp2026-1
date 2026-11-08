"""Export queue and worker. Databricks itself is replaced by a recording stand-in here so the tests run
offline; the real API path is exercised by running `python -m scripts.dbx_worker --once` with a .env."""
import json

import pytest

from app import databricks, db, service
from scripts import dbx_worker

FX = db.load_fixtures()


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("APP_MODE", "demo")
    for k in ("DATABRICKS_HOST", "DATABRICKS_WAREHOUSE_ID", "DATABRICKS_TOKEN"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(str(tmp_path / "test.db"))
    db.init_db(c)
    return c


def enable(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "dbc-test.cloud.databricks.com")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh")
    monkeypatch.setenv("DATABRICKS_TOKEN", "test-token")


def send(conn, key):
    a = FX["announcements"][key]
    return service.intake(conn, a["source_id"], a["external_id"], a["caption"], a["source_url"])


def queue(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM dbx_queue ORDER BY created_at, op_key")]


class Recorder:
    def __init__(self, fail_with=None):
        self.calls, self.fail_with = [], fail_with

    def __call__(self, kind, payload):
        self.calls.append((kind, payload))
        if self.fail_with:
            raise self.fail_with


def test_intake_queues_source_and_revision_in_same_commit(conn):
    out = send(conn, "A")
    kinds = sorted((r["kind"], r["version"]) for r in queue(conn))
    # raw source version (v1), linked outcome (v2) and the event's first revision
    assert kinds == [("announcement", 1), ("announcement", 2), ("revision", 1)]
    rev = next(json.loads(r["payload"]) for r in queue(conn) if r["kind"] == "revision")
    assert rev["event_id"] == out["event_id"] and rev["club_id"] == "demo-campus-coding-club"
    assert json.loads(rev["snapshot_json"])["venue"] == "Demo Hall 101"


def test_retry_of_same_post_adds_nothing(conn):
    send(conn, "A")
    before = len(queue(conn))
    assert send(conn, "A")["duplicate"] is True
    assert len(queue(conn)) == before


def test_backfill_queues_missing_records_without_replacing_existing_versions(conn):
    a = send(conn, "A")
    b = send(conn, "B")
    conn.execute("DELETE FROM dbx_queue WHERE aggregate IN (?, ?)", (a["announcement_id"], a["event_id"]))
    conn.commit()
    existing = [row for row in queue(conn) if row["aggregate"] == b["announcement_id"]]

    assert dbx_worker.backfill(conn) == {"announcements": 1, "revisions": 1}
    assert dbx_worker.backfill(conn) == {"announcements": 0, "revisions": 0}
    rows = queue(conn)
    assert [row for row in rows if row["aggregate"] == b["announcement_id"]] == existing
    announcement, = [row for row in rows if row["aggregate"] == a["announcement_id"]]
    assert json.loads(announcement["payload"])["status"] == "linked"
    assert any(row["kind"] == "revision" and row["aggregate"] == a["event_id"] for row in rows)


def test_review_and_confirm_export_outcome_and_new_revision(conn):
    a = send(conn, "A")
    c = send(conn, "C")
    statuses = [json.loads(r["payload"])["status"] for r in queue(conn)
                if r["kind"] == "announcement" and r["aggregate"] == c["announcement_id"]]
    assert statuses == ["pending", "review"]
    service.resolve_review(conn, c["review_id"], "confirm", 1, "tester")
    revs = [r["version"] for r in queue(conn) if r["kind"] == "revision" and r["aggregate"] == a["event_id"]]
    assert revs == [1, 2]


def test_worker_does_nothing_when_disabled(conn):
    send(conn, "A")
    rec = Recorder()
    assert dbx_worker.run_once(conn, export=rec) == {"enabled": False, "claimed": 0, "exported": 0, "retrying": 0}
    assert rec.calls == [] and all(r["state"] == "pending" for r in queue(conn))
    assert service.dbx_status(conn)["enabled"] is False


def test_worker_exports_everything_once(conn, monkeypatch):
    enable(monkeypatch)
    send(conn, "A")
    rec = Recorder()
    summary = dbx_worker.run_once(conn, export=rec)
    assert summary["exported"] == 3 and len(rec.calls) == 3
    assert all(r["state"] == "done" for r in queue(conn))
    assert dbx_worker.run_once(conn, export=rec)["claimed"] == 0  # nothing re-sent
    assert service.dbx_status(conn)["exported"] == 3


def test_databricks_outage_keeps_app_working_and_retries_later(conn, monkeypatch):
    enable(monkeypatch)
    send(conn, "A")
    dbx_worker.run_once(conn, export=Recorder(fail_with=databricks.DatabricksError("HTTP 503")))
    rows = queue(conn)
    assert all(r["state"] == "pending" and r["attempts"] == 1 and "503" in r["last_error"] for r in rows)
    assert send(conn, "B")["outcome"] == "linked"  # intake unaffected by the outage
    # not due yet: backoff holds the failed rows back
    assert dbx_worker.run_once(conn, export=Recorder())["claimed"] == len(queue(conn)) - len(rows)


def test_timed_out_statement_is_reconciled_not_resent(conn, monkeypatch):
    enable(monkeypatch)
    send(conn, "A")
    dbx_worker.run_once(conn, export=Recorder(fail_with=databricks.StatementPending("stmt-1")))
    assert {r["statement_id"] for r in queue(conn)} == {"stmt-1"}
    conn.execute("UPDATE dbx_queue SET next_retry_at='2000-01-01T00:00:00+00:00'")
    conn.commit()
    rec = Recorder()
    summary = dbx_worker.run_once(conn, export=rec, statement_state=lambda sid: "SUCCEEDED")
    assert summary["exported"] == 3 and rec.calls == []


def test_crashed_worker_claim_is_recovered(conn, monkeypatch):
    enable(monkeypatch)
    send(conn, "A")
    dbx_worker.claim(conn)  # worker claims, then "crashes" without recording anything
    assert dbx_worker.claim(conn) == []  # lease still held
    conn.execute("UPDATE dbx_queue SET claim_expires='2000-01-01T00:00:00+00:00'")
    conn.commit()
    assert dbx_worker.run_once(conn, export=Recorder())["exported"] == 3


def test_announcement_merge_ignores_older_versions():
    sql = databricks.merge_announcement_sql()
    assert "s.projection_version > t.projection_version" in sql
    assert "WHEN MATCHED" not in databricks.merge_revision_sql()  # revisions are insert-only


def test_maritime_source_is_registered(conn):
    row = conn.execute("SELECT kind FROM sources WHERE source_id='src-maritime-feed'").fetchone()
    assert row["kind"] == "maritime_feed"
