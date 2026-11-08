"""End-to-end checks for fixtures A-D. Runs offline: with no GEMINI_API_KEY the extractor
uses the labelled fixture candidates."""
import os

import pytest

from app import db, service


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(str(tmp_path / "test.db"))
    db.init_db(c)
    return c


FX = db.load_fixtures()


def send(conn, key):
    a = FX["announcements"][key]
    return service.intake(conn, a["source_id"], a["external_id"], a["caption"], a["source_url"])


def outbox(conn):
    return [dict(r) for r in conn.execute("SELECT event_id, revision, kind FROM event_outbox ORDER BY revision")]


def test_a_creates_one_event_and_one_announcement(conn):
    out = send(conn, "A")
    assert out["outcome"] == "created"
    assert [o["kind"] for o in outbox(conn)] == ["new_event"]


def test_same_source_version_twice_is_idempotent(conn):
    first = send(conn, "A")
    second = send(conn, "A")
    assert second["duplicate"] is True and second["announcement_id"] == first["announcement_id"]
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    assert len(outbox(conn)) == 1


def test_b_mirror_links_without_new_alert(conn):
    a = send(conn, "A")
    b = send(conn, "B")
    assert b["event_id"] == a["event_id"]
    assert len(outbox(conn)) == 1
    ev = service.public_event(conn, service.get_event(conn, a["event_id"]))
    assert len(ev["sources"]) == 2


def test_c_room_change_waits_for_review_then_one_correction(conn):
    a = send(conn, "A")
    send(conn, "B")
    c = send(conn, "C")
    assert c["state"] == "review"
    assert service.get_event(conn, a["event_id"])["venue"] == "Demo Hall 101"  # public event untouched
    r = service.resolve_review(conn, c["review_id"], "confirm", 1, "tester")
    assert r["revision"] == 2
    assert service.get_event(conn, a["event_id"])["venue"] == "Demo Hall 204"
    assert [o["kind"] for o in outbox(conn)] == ["new_event", "correction"]


def test_review_resolved_twice_or_stale_is_409_style(conn):
    send(conn, "A")
    c = send(conn, "C")
    with pytest.raises(service.ReviewConflict):
        service.resolve_review(conn, c["review_id"], "confirm", 99, "tester")  # wrong expected revision
    service.resolve_review(conn, c["review_id"], "confirm", 1, "tester")
    with pytest.raises(service.ReviewConflict):
        service.resolve_review(conn, c["review_id"], "confirm", 2, "tester")  # already resolved


def test_d_next_week_is_a_separate_event(conn):
    a = send(conn, "A")
    d = send(conn, "D")
    assert d["outcome"] == "created" and d["event_id"] != a["event_id"]


def test_correction_goes_only_to_recipients_of_original(conn):
    a = send(conn, "A")
    eid = a["event_id"]
    # sub-1 and sub-3 match; sub-2 follows a different topic
    assert sorted(service.dispatch_candidates(conn, eid, 1, "new_event")) == ["sub-1", "sub-3"]
    for sid in ("sub-1", "sub-3"):
        got = service.claim(conn, sid, eid, 1, "new_event")
        assert got["status"] == "claimed"
        service.record_result(conn, got["delivery_id"], got["claim_token"], "accepted", "msg-" + sid)
    # a retry of a finished delivery is skipped, not re-sent
    assert service.claim(conn, "sub-1", eid, 1, "new_event")["status"] == "skipped"
    # sub-3 unsubscribes, then the room changes
    conn.execute("UPDATE subscriptions SET opted_out_at='2026-11-08T00:00:00+00:00' WHERE subscriber_id='sub-3'")
    conn.commit()
    c = send(conn, "C")
    service.resolve_review(conn, c["review_id"], "confirm", 1, "tester")
    assert service.dispatch_candidates(conn, eid, 2, "correction") == ["sub-1"]
    msg = service.claim(conn, "sub-1", eid, 2, "correction")
    assert "Demo Hall 101 → Demo Hall 204" in msg["text"]
    assert service.claim(conn, "sub-3", eid, 2, "correction")["status"] == "skipped"


def test_missing_price_fails_free_filter(conn):
    send(conn, "A")
    conn.execute("UPDATE events SET cost_status='unknown'")
    conn.commit()
    assert service.list_events(conn, free=True, include_past=True) == []
    assert len(service.list_events(conn, include_past=True)) == 1


def test_perks_are_stored_and_public(conn):
    a, d = send(conn, "A"), send(conn, "D")
    assert service.public_event(conn, service.get_event(conn, a["event_id"]))["perks"] == ["free_food", "free_swag"]
    assert service.public_event(conn, service.get_event(conn, d["event_id"]))["perks"] == ["prizes"]


def test_audience_is_stored_and_filled_only_when_unstated(conn, monkeypatch):
    a, d = send(conn, "A"), send(conn, "D")
    assert service.get_event(conn, a["event_id"])["audience"] == ["anyone"]
    assert service.public_event(conn, service.get_event(conn, d["event_id"]))["audience"] == ["first_years", "cs_students"]
    # A mirror that names a different audience doesn't overwrite one that was stated...
    fx = db.load_fixtures()
    fx["candidates"]["B"]["audience"] = ["women"]
    monkeypatch.setattr("app.extract.load_fixtures", lambda: fx)
    send(conn, "B")
    assert service.get_event(conn, a["event_id"])["audience"] == ["anyone"]
    # ...but does fill it in when the original didn't say.
    conn.execute("UPDATE events SET audience='[]' WHERE event_id=?", (a["event_id"],))
    conn.commit()
    b = fx["announcements"]["B"]
    service.intake(conn, b["source_id"], "mirror-002", b["caption"], b["source_url"])
    assert service.get_event(conn, a["event_id"])["audience"] == ["women"]
    assert [o["kind"] for o in outbox(conn)].count("correction") == 0


def test_mirror_adds_new_perks_quietly(conn, monkeypatch):
    eid = send(conn, "A")["event_id"]
    conn.execute("UPDATE events SET perks='[\"free_food\"]'")
    conn.commit()
    fx = db.load_fixtures()
    fx["candidates"]["B"]["perks"] = ["free_food", "prizes"]
    monkeypatch.setattr("app.extract.load_fixtures", lambda: fx)
    send(conn, "B")
    ev = service.get_event(conn, eid)
    assert ev["perks"] == ["free_food", "prizes"]
    assert [o["kind"] for o in outbox(conn)] == ["new_event"]  # perks never trigger a correction


def test_old_database_gains_perks_column(tmp_path):
    c = db.connect(str(tmp_path / "old.db"))
    old_schema = "\n".join(l for l in db.SCHEMA.read_text(encoding="utf-8").splitlines() if "perks" not in l)
    c.executescript(old_schema)
    db.init_db(c)
    assert "perks" in {r["name"] for r in c.execute("PRAGMA table_info(events)")}
