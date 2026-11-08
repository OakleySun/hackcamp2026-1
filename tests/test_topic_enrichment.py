from datetime import datetime, timedelta

import pytest

from app import db, service, topic_enrichment
from app.models import Candidate


@pytest.fixture
def conn(monkeypatch):
    monkeypatch.setenv("APP_MODE", "production")
    with db.connect(":memory:") as conn:
        db.init_db(conn)
        conn.execute("INSERT INTO clubs (club_id, display_name) VALUES ('campus', 'Campus Club')")
        conn.execute("INSERT INTO sources (source_id, club_id, kind) VALUES ('calendar', 'campus', 'public_events')")
    yield conn
    conn.close()


def publish(conn, title, description="", external_id=None):
    tomorrow = datetime.now(service.VAN).date() + timedelta(days=1)
    result = service.intake(conn, "calendar", external_id or title, f"Title: {title}\nDescription: {description}",
                            "https://example.test/calendar", candidate=Candidate(title=title,
                                local_date=tomorrow.isoformat(), local_start="10:00"))
    return result["event_id"]


def test_gemini_backfills_existing_events_and_remembers_ambiguous_listings(conn):
    clinic = publish(conn, "Vaccination Clinic", "Walk-in influenza immunizations.")
    vague = publish(conn, "Friday Session", "More details soon.")
    already_tagged = publish(conn, "Volleyball")

    def classify(listings):
        assert not conn.in_transaction
        assert {listing.event_id for listing in listings} == {clinic, vague}
        return topic_enrichment.TopicBatch(assignments=[
            {"slot": slot, "topics": ["wellness"] if listing.event_id == clinic else []}
            for slot, listing in enumerate(listings, 1)
        ])

    assert topic_enrichment.run_batch(conn, classify) == (2, 1)
    assert topic_enrichment.run_batch(conn, classify) == (0, 0)
    assert [e["event_id"] for e in service.list_events(conn, topic="wellness")] == [clinic]
    assert service.get_event(conn, vague)["topics"] == []
    assert service.get_event(conn, already_tagged)["topics"] == ["sports"]
    assert conn.execute("SELECT count(*) FROM event_outbox").fetchone()[0] == 3
    assert conn.execute("SELECT 1 FROM dbx_queue WHERE aggregate=? AND kind='revision' AND version=2",
                        (clinic,)).fetchone()

    assert publish(conn, "Friday Session", "Try block printing with our instructor.") == vague
    result = topic_enrichment.TopicBatch(assignments=[{"slot": 1, "topics": ["arts"]}])
    assert topic_enrichment.run_batch(conn, lambda listings: result) == (1, 1)
    assert service.get_event(conn, vague)["topics"] == ["arts"]


def test_in_flight_result_preserves_a_new_tag_and_budget_is_persistent(conn, monkeypatch):
    event = publish(conn, "Vaccination Clinic")
    monkeypatch.setattr(topic_enrichment, "DAILY_REQUEST_LIMIT", 1)

    def classify(listings):
        assert [listing.event_id for listing in listings] == [event]
        with conn:
            service.update_event(conn, event, {"topics": ["academic"]}, "source tag")
        return topic_enrichment.TopicBatch(assignments=[{"slot": 1, "topics": ["wellness"]}])

    assert topic_enrichment.run_batch(conn, classify) == (1, 0)
    assert service.get_event(conn, event)["topics"] == ["academic"]
    publish(conn, "Friday Session")
    assert topic_enrichment.run_batch(conn, classify) == (0, 0)
