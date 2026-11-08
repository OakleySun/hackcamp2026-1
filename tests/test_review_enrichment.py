from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app import db, service
from app.main import app


def test_enrichment_publishes_verified_occurrence_once_and_keeps_unknown_organizer(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_MODE", "production")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "quad.db"))
    monkeypatch.setenv("REVIEW_ENRICHMENT_TOKEN", "worker")
    monkeypatch.setenv("REVIEWER_TOKEN", "reviewer")
    monkeypatch.setenv("SOURCE_INGEST_TOKEN", "intake")
    url = "https://events.ubc.ca/event/campus-market/2026-12-04/"
    event_date = (datetime.now(service.VAN).date() + timedelta(days=1)).isoformat()
    evidence = {"url": url, "title": "Campus Market", "organizer": "Market Society",
                "local_date": event_date, "local_start": "15:00", "venue": "Wesbrook Village"}
    worker = {"Authorization": "Bearer worker"}
    reviewer = {"Authorization": "Bearer reviewer"}
    with TestClient(app) as api:
        with db.connect() as conn:
            for source_id in ("src-ubc-events-home", "src-ubc-events-rss"):
                conn.execute("INSERT INTO sources(source_id,kind) VALUES(?,'public_events')", (source_id,))
        for source_id in ("src-ubc-events-home", "src-ubc-events-rss"):
            response = api.post("/api/intake", headers={"Authorization": "Bearer intake"}, json={
                "source_id": source_id, "external_id": "market", "source_url": url, "caption": "Market",
                "candidate": {"title": "Campus Market"},
            })
            assert response.json()["state"] == "review"
        pending_url = "https://events.ubc.ca/event/campus-exhibit/"
        response = api.post("/api/intake", headers={"Authorization": "Bearer intake"}, json={
            "source_id": "src-ubc-events-home", "external_id": "exhibit", "source_url": pending_url,
            "caption": "Exhibit", "candidate": {"title": "Campus Exhibit"},
        })
        assert response.json()["state"] == "review"

        assert api.get("/api/enrichment/work", headers=reviewer).status_code == 401
        queue = api.get("/api/enrichment/work", headers=worker).json()
        assert len(queue) == 2
        ids = {item["title"]: item["review_id"] for item in queue}
        batch = {"results": [
            {"review_id": ids["Campus Market"], "finding": evidence},
            {"review_id": ids["Campus Exhibit"], "finding": {**evidence, "url": pending_url,
                "title": "Campus Exhibit", "organizer": None}},
        ]}
        assert api.post("/api/enrichment/results", json=batch).status_code == 401
        assert api.post("/api/enrichment/results", headers=worker, json=batch).json() == {
            "suggestions": 2, "published": 1, "linked": 0, "unresolved": 1,
        }
        assert api.get("/api/reviews/enrichment", headers=worker).status_code == 401
        inbox = api.get("/api/reviews/enrichment", headers=reviewer).json()
        assert len(inbox) == 1 and inbox[0]["candidate"]["title"] == "Campus Exhibit"
        assert api.post("/api/enrichment/results", headers=worker, json=batch).json() == {
            "suggestions": 1, "published": 0, "linked": 0, "unresolved": 1,
        }
        events = api.get("/api/events").json()
        assert len(events) == 1 and events[0]["local_date"] == event_date
        assert len(events[0]["sources"]) == 2
