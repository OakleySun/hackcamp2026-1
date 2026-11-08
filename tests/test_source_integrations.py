"""Exercise the monitor, Gemini SDK, and intake together without external credentials."""

import base64
import json

import httpx
from fastapi.testclient import TestClient
from google import genai
from google.genai import types

from app.main import app
from scripts.check_sources import check_source

FLYER = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a53sAAAAASUVORK5CYII="
)


def test_monitored_flyer_retry_duplicate_and_room_change(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_MODE", "demo")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "monitor.db"))
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-flash-model")
    monkeypatch.setenv("SOURCE_INGEST_TOKEN", "test-intake-token")
    monkeypatch.setenv("REVIEWER_TOKEN", "test-review-token")
    monkeypatch.setenv("WORKFLOW_API_TOKEN", "test-workflow-token")
    venue = "Demo Hall 101"
    provider_calls = []

    def generate(request):
        body = json.loads(request.content)
        provider_calls.append(body)
        assert "test-flash-model" in request.url.path
        assert request.headers["x-goog-api-key"] == "test-gemini-key"
        assert "responseSchema" in body["generationConfig"]
        assert body["systemInstruction"]["parts"][0]["text"].startswith("Extract one club event")
        inline_data = body["contents"][0]["parts"][1]["inlineData"]["data"]
        assert base64.urlsafe_b64decode(inline_data) == FLYER
        if len(provider_calls) == 1:
            return httpx.Response(503, json={"error": {"code": 503, "message": "temporarily unavailable"}})
        candidate = {
            "title": "Intro to Git",
            "local_date": "2026-11-12",
            "local_start": "17:00",
            "venue": venue,
            "cost_status": "free",
            "beginner_friendly": True,
            "topics": ["tech", "invented-topic"],
            "rsvp_url": "https://unverified.example.test/rsvp",
        }
        return httpx.Response(200, json={
            "candidates": [{"content": {"role": "model", "parts": [{"text": json.dumps(candidate)}]}}],
        })

    actual_client = genai.Client
    with httpx.Client(transport=httpx.MockTransport(generate)) as gemini_transport, TestClient(app) as api:
        def fake_gemini(**kwargs):
            kwargs["http_options"].httpx_client = gemini_transport
            kwargs["http_options"].retry_options = types.HttpRetryOptions(attempts=1)
            return actual_client(**kwargs)

        monkeypatch.setattr(genai, "Client", fake_gemini)

        def connect(request):
            if request.url.host == "feed.example.test":
                assert "authorization" not in request.headers
                if request.url.path == "/flyer.png":
                    return httpx.Response(200, content=FLYER)
                return httpx.Response(200, json={"events": [{
                    "external_id": "intro-git",
                    "source_url": "https://feed.example.test/intro-git",
                    "caption": f"Intro to Git, Nov 12, 2026 at 5 PM, {venue}.",
                    "flyer_url": "https://feed.example.test/flyer.png",
                }]})
            assert request.url.host == "app.example.test"
            response = api.request(request.method, request.url.raw_path.decode(),
                                   headers=dict(request.headers), content=request.read())
            return httpx.Response(response.status_code, content=response.content)

        with httpx.Client(transport=httpx.MockTransport(connect)) as monitor:
            args = (monitor, "https://feed.example.test/feed.json", "https://app.example.test",
                    "src-demo-feed", "test-intake-token")
            assert check_source(*args)["failed"] == 1
            assert api.get("/api/events?include_past=true").json() == []
            assert check_source(*args)["submitted"] == 1
            assert check_source(*args)["unchanged"] == 1
            assert len(provider_calls) == 2
            event, = api.get("/api/events?include_past=true").json()
            assert event["venue"] == "Demo Hall 101"
            assert event["cost_status"] == "unknown"
            assert event["beginner_friendly"] is None
            assert event["rsvp_url"] is None
            assert event["topics"] == ["tech"]

            venue = "Demo Hall 204"
            assert check_source(*args)["review"] == 1
            assert api.get(f"/api/events/{event['event_id']}").json()["venue"] == "Demo Hall 101"
            reviewer = {"Authorization": "Bearer test-review-token"}
            review, = api.get("/api/reviews", headers=reviewer).json()
            approved = api.post(f"/api/reviews/{review['review_id']}/resolve", headers=reviewer,
                                json={"decision": "confirm", "expected_revision": 1})
            assert approved.status_code == 200
            assert api.get(f"/api/events/{event['event_id']}").json()["venue"] == "Demo Hall 204"
            workflow = {"Authorization": "Bearer test-workflow-token"}
            outbox = api.get("/internal/outbox/pending", headers=workflow).json()
            assert [row["kind"] for row in outbox] == ["new_event", "correction"]


def test_checker_rejects_off_origin_flyer():
    def feed(request):
        assert request.url == "https://feed.example.test/feed.json"
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"events": [{
            "external_id": "off-origin",
            "source_url": "https://feed.example.test/event",
            "flyer_url": "https://other.example.test/private",
        }]})

    with httpx.Client(transport=httpx.MockTransport(feed)) as client:
        result = check_source(client, "https://feed.example.test/feed.json",
                              "https://app.example.test", "src-demo-feed", "test-token")
    assert result == {"checked": 1, "submitted": 0, "unchanged": 0, "review": 0, "failed": 1}
