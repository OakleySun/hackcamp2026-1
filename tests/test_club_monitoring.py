"""Directory coverage, explicit dates, and bounded Instagram intake without network/model calls."""

from datetime import datetime, timezone
import json

import httpx
import pytest

from scripts.club_directory import channels, directory_page, instagram_url, public_url
from scripts.club_sites import site_listings
from scripts.instagram_monitor import check, post_listing
from scripts.public_sources import public_feed

NOW = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)


def test_directory_uses_all_pages_and_only_explicit_channels():
    page = '''<p>(317) clubs found</p><div class="club-item"><a class="club-item-link"
      href="https://amsclubs.ca/example-club/"><h2>Example Club</h2><span>Discover</span></a></div>
      <a href="/all-clubs//pagenum/36/">Last</a>'''
    clubs, pages, expected = directory_page(page)
    assert (len(clubs), pages, expected) == (1, 36, 317)
    links = '''<nav><a href="https://www.instagram.com/ams_ubc/">AMS</a></nav>
      <div class="club-sm"><a href="https://instagram.com/example_club/?hl=en">Club</a>
      <a href="https://club.example.org/">Website</a><a href="https://instagram.com/p/abc/">Post</a></div>'''
    found = channels(links, clubs[0]["directory_url"])
    assert found["instagram_urls"] == ["https://www.instagram.com/example_club/"]
    assert found["website_urls"] == ["https://club.example.org/"]
    assert instagram_url("https://instagram.com/p/abc/") is None
    for url in ("https://127.0.0.1/", "http://backend.private/", "https://user:pass@example.org/"):
        with pytest.raises(ValueError):
            public_url(url)


def test_biztech_date_range_keeps_unknown_times_and_deduplicates_layouts():
    card = '''<div data-framer-name="ContentArea"><p>November 26-30, 2026</p><p>KickStart</p>
      <p>A 5-day startup competition.</p><a href="/events/kickstart-2026">Apply now</a></div>'''
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=card * 2))) as client:
        event, = public_feed(client, "https://www.ubcbiztech.com/events", "biztech", now=NOW)["events"]
    assert event["candidate"]["local_date"] == "2026-11-26"
    assert event["candidate"]["local_start"] is None
    assert event["candidate"]["cost_status"] == "unknown"
    assert "November 26-30, 2026" in event["caption"]


def test_club_site_structured_events_and_unstructured_text_have_different_review_paths():
    club = {"club_id": "example", "name": "Example Club"}
    page = '''<script type="application/ld+json">{"@context":"https://schema.org", "@type":"Event",
      "name":"Fall Workshop", "startDate":"2026-11-13T17:00:00-07:00",
      "url":"https://club.example.org/events/fall", "location":{"name":"DMP 110"}}</script>'''
    structured, = site_listings(page, "https://club.example.org/", club, NOW)
    assert structured["candidate"]["local_date"] == "2026-11-13"
    assert structured["candidate"]["local_start"] == "17:00"
    raw, = site_listings("<main>Fall Workshop, November 13, 2026. Details coming soon.</main>",
                         "https://club.example.org/events/", club, NOW)
    assert raw["candidate"]["local_date"] is None
    assert site_listings("<main>Join our club!</main>", "https://club.example.org/", club, NOW) == []


@pytest.mark.parametrize("browser_status", ["ok", "login_required", "rate_limited"])
def test_instagram_window_runs_once_stops_for_auth_and_sleeps(tmp_path, monkeypatch, browser_status):
    from scripts import instagram_monitor

    account = {"club": "Example Club", "url": "https://www.instagram.com/example_club/",
               "clubs": [{"club_id": "example", "name": "Example Club"}]}
    watchlist = tmp_path / "watchlist.json"
    watchlist.write_text(json.dumps({"accounts": [account]}))
    monkeypatch.setenv("MARITIME_INSTAGRAM_ENABLED", "true")
    monkeypatch.setenv("MARITIME_COMPUTERS_KEY", "test-computers-key")
    monkeypatch.setenv("MARITIME_INSTAGRAM_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(instagram_monitor.time, "sleep", lambda n: None)
    calls, submissions = [], []
    post = {"url": "https://www.instagram.com/p/abc123/", "caption": "Posted November 8. Workshop soon!", "image_alt": []}

    def api(request):
        calls.append(request.url.path)
        assert request.headers["authorization"] == "Bearer test-computers-key"
        if request.url.path.endswith("/exec"):
            return httpx.Response(200, json={"exitCode": 0, "stdout": json.dumps({"status": browser_status,
                "posts": [post] if browser_status == "ok" else []})})
        return httpx.Response(200, json={"mode": "agent", "status": "sleeping"})

    def intake(request):
        submissions.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer intake-token"
        return httpx.Response(202, json={"duplicate": False, "state": "review"})

    original_client = httpx.Client
    with original_client(transport=httpx.MockTransport(intake)) as backend:
        monkeypatch.setattr(instagram_monitor.httpx, "Client",
                            lambda **kwargs: original_client(transport=httpx.MockTransport(api), **kwargs))
        options = {"computer_id": "existing-computer", "watchlist": str(watchlist)}
        result = check(backend, "https://app.example.org", "instagram", "intake-token", "", options)
        assert result["accounts_checked"] == 1
        assert calls[-1].endswith("/sleep")
        count = len(calls)
        repeated = check(backend, "https://app.example.org", "instagram", "intake-token", "", options)
        assert len(calls) == count
        if browser_status == "ok":
            assert result["review"] == 1
            assert submissions[0]["candidate"]["local_date"] is None
            assert repeated["browser_status"] == "already_checked_this_window"
        else:
            assert result["failed"] == 1
            assert repeated["cooldown_until"]
            assert not submissions
