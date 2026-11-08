import json
from datetime import datetime, timedelta

import httpx
from fastapi.testclient import TestClient

from app import databricks, db, service
from app.main import app


def test_genie_only_returns_eligible_events_and_respects_the_daily_limit(tmp_path, monkeypatch):
    path = str(tmp_path / "genie.db")
    monkeypatch.setenv("DATABASE_PATH", path)
    monkeypatch.setenv("APP_MODE", "production")
    monkeypatch.setenv("DATABRICKS_HOST", "example.test")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "warehouse")
    monkeypatch.setenv("DATABRICKS_TOKEN", "test-token")
    monkeypatch.setenv("GENIE_SPACE_ID", "1" * 32)
    monkeypatch.setenv("GENIE_DAILY_LIMIT", "1")
    today = datetime.now(service.VAN).date()
    tomorrow = (today + timedelta(days=1)).isoformat()
    with db.connect(path) as conn:
        db.init_db(conn, seed=False)
        conn.execute("INSERT INTO clubs(club_id, display_name) VALUES ('ubc', 'UBC')")
        conn.execute("INSERT INTO sources(source_id, kind) VALUES ('src-public', 'icalendar')")
        rows = [
            ("evt-1", "Intro to Machine Learning", "published", tomorrow, "free", "linked"),
            ("evt-2", "AI for Beginners", "published", tomorrow, "free", "linked"),
            ("evt-3", "Running Club", "published", tomorrow, "free", "linked"),
            ("evt-4", "AI Workshop", "cancelled", tomorrow, "free", "linked"),
            ("evt-5", "AI Workshop", "published", tomorrow, "free", "review"),
            ("evt-6", "AI Workshop", "published", tomorrow, "unknown", "linked"),
        ]
        for event_id, title, state, day, cost, source_status in rows:
            conn.execute("""INSERT INTO events(event_id, club_id, title, state, local_date, cost_status)
                            VALUES (?, 'ubc', ?, ?, ?, ?)""", (event_id, title, state, day, cost))
            conn.execute("""INSERT INTO source_announcements(announcement_id, source_id, external_id, source_url,
                            content_hash, detected_at, status, event_id)
                            VALUES (?, 'src-public', ?, ?, 'hash', ?, ?, ?)""",
                         (event_id, event_id, f"https://example.test/{event_id}", day, source_status, event_id))

    submissions = []

    def respond(request):
        if request.url.path.endswith("/start-conversation"):
            submissions.append(json.loads(request.content)["content"])
            return httpx.Response(200, json={"conversation_id": "c", "message_id": "m", "message": {
                "status": "COMPLETED", "attachments": [{"attachment_id": "a", "query": {"title": "events"}}],
            }})
        return httpx.Response(200, json={"statement_response": {
            "manifest": {"schema": {"columns": [{"name": "event_id"}]}},
            "result": {"data_array": [[event_id] for event_id in ("evt-3", "evt-4", "evt-5", "evt-6", "evt-2")]},
        }})

    monkeypatch.setattr(databricks, "_client", lambda **_: httpx.Client(
        base_url="https://example.test", transport=httpx.MockTransport(respond)))
    api = TestClient(app)
    response = api.post("/api/genie", json={"question": "Give me three free events to learn about AI"})
    assert response.status_code == 200
    data = response.json()
    assert data["engine"] == "genie" and data["matched"] == 2
    assert [event["event_id"] for event in data["events"]] == ["evt-2", "evt-1"]
    assert all("https://example.test/" in event["source_url"] for event in data["events"])
    assert len(submissions) == 1 and "evt-3" not in submissions[0] and "learn about AI" not in submissions[0]

    response = api.post("/api/genie", json={"question": "Give me three running events"}).json()
    assert response["engine"] == "quad" and response["matched"] == 1
    assert response["events"][0]["event_id"] == "evt-3"
    assert len(submissions) == 1
