"""Public source boundaries, pagination, review routing and no-cost structured intake."""

from datetime import datetime, timezone

import httpx
from fastapi.testclient import TestClient
import pytest

from app import db, service
from app.main import app
from scripts import check_sources
from scripts.public_sources import public_feed
from scripts.setup_sources import register_sources

NOW = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)


def card(day="13", venue="Buchanan", club="UBC Anime Club"):
    return f'''<div class="event-wrap"><a href="https://amsclubs.ca/anime-club/event/weekly/2026-11-{day}/">
    <h3>UBCAni Friday Weekly</h3><p class="event-details"><strong>Club: {club}</strong><br>
    Location: {venue}<br>Date: Nov {day}, 2026<br>Time: 05:00 PM - 09:30 PM</p></a>
    <p class="event-description">Weekly gathering</p></div>'''


RSS = b'''<rss version="2.0"><channel><item><title>Campus Workshop</title>
<link>https://events.ubc.ca/event/workshop/</link><guid>workshop-1</guid>
<pubDate>Fri, 13 Nov 2026 17:00:00 +0000</pubDate><description>Details to follow.</description>
</item></channel></rss>'''


def test_ams_pagination_deduplicates_and_keeps_occurrence_identity():
    venue, urls = "Buchanan", []

    def pages(request):
        urls.append(str(request.url))
        assert "authorization" not in request.headers
        if request.url.path == "/all-events/":
            return httpx.Response(200, text=card(venue=venue) +
                                  '<a class="next-page" href="https://amsclubs.ca/all-events//pagenum/2/">Next</a>')
        assert request.url.path == "/all-events/pagenum/2/"
        return httpx.Response(200, text=card(venue=venue) + card("20"))

    with httpx.Client(transport=httpx.MockTransport(pages)) as client:
        def read():
            return public_feed(client, "https://amsclubs.ca/all-events/", "ams_html", now=NOW,
                               options={"organizers": {"UBC Anime Club": "ubc-anime"}})["events"]
        first = read()
        assert len(first) == 2 and len(urls) == 2
        assert first[0]["external_id"] != first[1]["external_id"]
        assert first[0]["candidate"]["local_start"] == "17:00"
        assert first[0]["candidate"]["organizer_slug"] == "ubc-anime"
        venue = "Buchanan 204"
        updated = read()
        assert updated[0]["external_id"] == first[0]["external_id"]
        assert updated[0]["candidate"]["venue"] == venue


def test_source_failure_does_not_stop_other_feeds_or_leak_token():
    def transport(request):
        assert "authorization" not in request.headers
        if request.url.host == "amsclubs.ca":
            return httpx.Response(403)
        return httpx.Response(200, text='<script id="__NEXT_DATA__">{"props":{"pageProps":'
                              '{"initialData":{"data":{"upcoming":{"entries":[],"has_more":false}}}}}}</script>')

    sources = [{"source_id": "ams", "url": "https://amsclubs.ca/all-events/", "format": "ams_html"},
               {"source_id": "launchpad", "url": "https://luma.com/launchpadubc", "format": "luma"}]
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        result = check_sources.check_sources(client, sources, "https://app.example.test", "private-token")
    assert result["failed"] == 1
    assert result["sources"][0]["error"] == "HTTP 403"
    assert result["sources"][1]["status"] == "succeeded"
    assert result["sources"][1]["checked"] == 0


def test_public_intake_replay_correction_and_rss_review_without_gemini(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_MODE", "production")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "sources.db"))
    monkeypatch.setenv("SOURCE_INGEST_TOKEN", "test-token")
    monkeypatch.setenv("REVIEWER_TOKEN", "test-review")
    monkeypatch.setattr(service, "extract", lambda *a, **k: pytest.fail("Public adapters must not call a model"))
    actual_adapter = check_sources.public_feed
    monkeypatch.setattr(check_sources, "public_feed", lambda *a, **k: actual_adapter(*a, **k, now=NOW))
    venue, club = "Buchanan", "UBC Anime Club"

    with TestClient(app) as api:
        conn = db.connect()
        try:
            register_sources(conn)
            register_sources(conn)
            assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 6
            assert conn.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0] == 0
        finally:
            conn.close()

        def transport(request):
            if request.url.host in ("amsclubs.ca", "events.ubc.ca"):
                assert "authorization" not in request.headers
                return httpx.Response(200, content=RSS if request.url.host == "events.ubc.ca"
                                      else card(venue=venue, club=club).encode())
            response = api.request(request.method, request.url.raw_path.decode(),
                                   headers=dict(request.headers), content=request.read())
            return httpx.Response(response.status_code, content=response.content)

        with httpx.Client(transport=httpx.MockTransport(transport)) as client:
            args = (client, "https://amsclubs.ca/all-events/", "https://app.example.test", "src-ams-clubs", "test-token")
            options = {"organizers": {"UBC Anime Club": "ubc-anime"}}
            assert check_sources.check_source(*args, feed_format="ams_html", options=options)["submitted"] == 1
            assert check_sources.check_source(*args, feed_format="ams_html", options=options)["unchanged"] == 1
            venue = "Buchanan 204"
            assert check_sources.check_source(*args, feed_format="ams_html", options=options)["review"] == 1
            event, = api.get("/api/events?include_past=true").json()
            assert event["venue"] == "Buchanan"
            club = "Unverified Club"
            assert check_sources.check_source(*args, feed_format="ams_html", options=options)["review"] == 1
            rss = public_feed(client, "https://events.ubc.ca/events/feed/", "rss")["events"][0]
            assert rss["candidate"]["local_date"] is None and rss["candidate"]["local_start"] is None
            assert check_sources.check_source(client, "https://events.ubc.ca/events/feed/", "https://app.example.test",
                                              "src-ubc-events-rss", "test-token", feed_format="rss")["review"] == 1
            assert len(api.get("/api/events?include_past=true").json()) == 1


def test_malformed_public_documents_fail_explicitly():
    for feed_format in ("rss", "luma", "ams_html", "tribe"):
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="{}"))) as client:
            with pytest.raises(ValueError):
                public_feed(client, "https://example.org/calendar", feed_format, now=NOW)
