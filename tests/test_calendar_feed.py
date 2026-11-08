"""Calendar identities, filtering and real-mode intake, without model/network charges."""

from datetime import datetime, timezone

import httpx
from fastapi.testclient import TestClient
import pytest

from app import db, service
from app.main import app
from scripts import check_sources
from scripts.calendar_feed import calendar_feed, CSSS_FEED_URL, CSSS_SOURCE_ID
from scripts.setup_csss import register_csss

NOW = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)


def calendar(*events):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Club Alerts Test//EN\r\n"
            "X-WR-CALNAME:UBC CS Events\r\n" + "".join(
                "BEGIN:VEVENT\r\n" + event.strip().replace("\n", "\r\n") + "\r\nEND:VEVENT\r\n"
                for event in events) + "END:VCALENDAR\r\n").encode()


EVENT = """UID:csss-study@google.com
DTSTAMP:20261101T000000Z
DTSTART:20261114T010000Z
DTEND:20261114T020000Z
SUMMARY:CSSS Fall Study Cafe
LOCATION:DMP 110
DESCRIPTION:Bring your notes. <a href="https://example.org/details">Details</a>
STATUS:CONFIRMED"""


def test_calendar_filters_non_events_and_preserves_explicit_fields():
    excluded = [EVENT.replace("csss-study@", f"hold-{n}@").replace("CSSS Fall Study Cafe", title)
                for n, title in enumerate(("[HOLD] CSSS Amazon", "Reading Break", "CSSRC Weekly Planning Meeting",
                                           "CSSS Internal Meeting", "Academic Break", "weekly tcf meeting"))]
    all_day = """UID:conference@google.com
DTSTART;VALUE=DATE:20261121
DTEND;VALUE=DATE:20261122
SUMMARY:CAN-CWIC Conference"""
    data = calendar(EVENT, *excluded, all_day,
                    EVENT.replace("csss-study@", "cancelled@").replace("CONFIRMED", "CANCELLED"),
                    EVENT.replace("20261114", "20251114").replace("csss-study@", "old@"))
    events = calendar_feed(data, now=NOW)["events"]
    assert len(events) == 2
    candidate = events[0]["candidate"]
    assert candidate["organizer_slug"] == "ubc-csss"
    assert (candidate["local_date"], candidate["local_start"], candidate["local_end"]) == ("2026-11-13", "18:00", "19:00")
    assert candidate["venue"] == "DMP 110"
    assert candidate["cost_status"] == "unknown" and candidate["beginner_friendly"] is None
    assert candidate["rsvp_url"] is None
    assert "https://example.org/details" in events[0]["caption"]
    assert events[1]["candidate"]["local_start"] is None
    assert events[1]["candidate"]["organizer_slug"] is None


def test_recurrence_exdates_and_moved_occurrence_keep_original_identity():
    series = """UID:weekly@google.com
DTSTART;TZID=America/Vancouver:20261113T150000
DTEND;TZID=America/Vancouver:20261113T160000
RRULE:FREQ=WEEKLY;COUNT=3
EXDATE;TZID=America/Vancouver:20261120T150000
SUMMARY:WiCS Tea with Grads
LOCATION:ICCS 304"""
    original = calendar_feed(calendar(series), now=NOW)["events"]
    assert len(original) == 2
    assert original[0]["external_id"] != original[1]["external_id"]
    moved = """UID:weekly@google.com
RECURRENCE-ID;TZID=America/Vancouver:20261127T150000
DTSTART;TZID=America/Vancouver:20261128T160000
DTEND;TZID=America/Vancouver:20261128T170000
SUMMARY:WiCS Tea with Grads
LOCATION:ICCS 204"""
    changed = calendar_feed(calendar(series, moved), now=NOW)["events"]
    assert len(changed) == 2
    assert changed[1]["external_id"] == original[1]["external_id"]
    assert changed[1]["candidate"]["local_date"] == "2026-11-28"
    assert changed[1]["candidate"]["venue"] == "ICCS 204"
    moved_single = calendar_feed(calendar(EVENT.replace("20261114T", "20261115T")), now=NOW)["events"][0]
    assert moved_single["external_id"] == calendar_feed(calendar(EVENT), now=NOW)["events"][0]["external_id"]


def test_real_mode_calendar_intake_replays_and_reviews_without_gemini(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_MODE", "production")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "calendar.db"))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("SOURCE_INGEST_TOKEN", "test-token")
    monkeypatch.setenv("REVIEWER_TOKEN", "test-review")
    data = calendar(EVENT)

    def no_model(*args, **kwargs):
        pytest.fail("Structured calendar intake must not call Gemini")

    monkeypatch.setattr(service, "extract", no_model)
    actual_adapter = check_sources.calendar_feed
    monkeypatch.setattr(check_sources, "calendar_feed", lambda content, **kwargs: actual_adapter(content, now=NOW))
    with TestClient(app) as api:
        conn = db.connect()
        try:
            register_csss(conn)
            register_csss(conn)
            assert conn.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0] == 0
        finally:
            conn.close()

        def transport(request):
            if request.url.host == "calendar.google.com":
                assert "authorization" not in request.headers
                return httpx.Response(200, content=data)
            response = api.request(request.method, request.url.raw_path.decode(),
                                   headers=dict(request.headers), content=request.read())
            return httpx.Response(response.status_code, content=response.content)

        with httpx.Client(transport=httpx.MockTransport(transport)) as client:
            args = (client, CSSS_FEED_URL, "https://app.example.test", CSSS_SOURCE_ID, "test-token")
            assert check_sources.check_source(*args, feed_format="ical")["submitted"] == 1
            data = calendar(EVENT.replace("20261101T000000Z", "20261108T000000Z"))
            assert check_sources.check_source(*args, feed_format="ical")["unchanged"] == 1
            event, = api.get("/api/events?include_past=true").json()
            data = calendar(EVENT.replace("DMP 110", "DMP 204"))
            assert check_sources.check_source(*args, feed_format="ical")["review"] == 1
            assert api.get(f"/api/events/{event['event_id']}").json()["venue"] == "DMP 110"
            data = calendar(EVENT.replace("csss-study@", "unknown@").replace("CSSS Fall Study Cafe", "AlgaeCal"))
            assert check_sources.check_source(*args, feed_format="ical")["review"] == 1


def test_calendar_rejects_malformed_and_unbounded_recurrence():
    with pytest.raises(ValueError):
        calendar_feed(b"not a calendar", now=NOW)
    with pytest.raises(ValueError, match="too frequent"):
        calendar_feed(calendar(EVENT + "\nRRULE:FREQ=SECONDLY"), now=NOW)


def test_private_http_requires_an_explicit_matching_maritime_backend():
    url = "http://backend.club-alerts.private:20001"
    with pytest.raises(ValueError):
        check_sources._service_url(url)
    assert str(check_sources._service_url(url, "backend.club-alerts.private")) == url
    with pytest.raises(ValueError):
        check_sources._service_url("http://other.private:20001", "backend.club-alerts.private")
    with pytest.raises(ValueError):
        check_sources._service_url("http://public.example.org", "public.example.org")
