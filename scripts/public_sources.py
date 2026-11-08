"""Bounded adapters for public calendars and announcements; no model calls or logins."""

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from scripts.calendar_feed import EXCLUDED_TITLE, VANCOUVER, plain_text

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024


def download(client, url):
    endpoint = httpx.URL(url)
    if endpoint.scheme != "https" or not endpoint.host or endpoint.userinfo:
        raise ValueError("Public sources require HTTPS")
    data = bytearray()
    with client.stream("GET", endpoint, follow_redirects=False,
                       headers={"User-Agent": "ClubAlerts/0.1 (+https://github.com/freddyp3/hackcamp2026)"}) as response:
        response.raise_for_status()
        if response.is_redirect:
            raise ValueError("Use the source's canonical URL")
        for chunk in response.iter_bytes():
            if len(data) + len(chunk) > MAX_DOCUMENT_BYTES:
                raise ValueError("Public source exceeds the size limit")
            data.extend(chunk)
    return bytes(data)


def _listing(identity, url, title, start=None, end=None, venue=None, organizer=None,
             description="", cost="unknown", all_day=False):
    candidate = {
        "organizer_slug": organizer, "title": title,
        "local_date": start.date().isoformat() if start else None,
        "local_start": start.strftime("%H:%M") if start and not all_day else None,
        "local_end": end.strftime("%H:%M") if end and start and not all_day
        and end.date() == start.date() else None,
        "timezone": "America/Vancouver", "venue": venue or None,
        "cost_status": cost, "beginner_friendly": None, "topics": [], "rsvp_url": None,
    }
    caption = "\n".join(filter(None, (
        f"Title: {title}", f"Date: {candidate['local_date']}" if start else "Event date: not provided by this feed",
        f"Start: {candidate['local_start']} (America/Vancouver)" if candidate["local_start"] else None,
        f"End: {end.isoformat()}" if end else None,
        f"Venue: {venue}" if venue else None,
        f"Description: {description[:8000]}" if description else None,
    )))
    return {"external_id": "public:" + hashlib.sha256(identity.encode()).hexdigest(),
            "source_url": url, "caption": caption, "candidate": candidate}


def _window(now, days):
    if not 1 <= days <= 180:
        raise ValueError("Source lookahead must be between 1 and 180 days")
    start = (now or datetime.now(timezone.utc)).astimezone(VANCOUVER)
    return start, start + timedelta(days=days)


def ams_page(data, *, now=None, days=60, organizers=None):
    """Read AMS's explicit club/date/time fields; preserve each occurrence's source URL."""
    lower, upper = _window(now, days)
    soup = BeautifulSoup(data, "html.parser")
    cards = soup.select(".event-wrap")
    if not cards and not re.search(r"no (?:upcoming )?events", soup.get_text(" "), re.I):
        raise ValueError("AMS event page format changed")
    result, dates = [], []
    organizers = organizers or {}
    for card in cards:
        heading = card.select_one("h3")
        details = card.select_one(".event-details")
        link = heading.find_parent("a") if heading else None
        if not heading or not details or not link:
            raise ValueError("AMS listing is missing explicit fields")
        text = " ".join(details.stripped_strings)
        match = re.fullmatch(r"Club:\s*(.*?)\s+Location:\s*(.*?)\s+Date:\s*"
                             r"([A-Za-z]{3} \d{1,2}, \d{4})\s+Time:\s*(.*)", text)
        if not match:
            raise ValueError("AMS date/time format changed")
        name, venue, date_text, time_text = match.groups()
        date = datetime.strptime(date_text, "%b %d, %Y").replace(tzinfo=VANCOUVER)
        dates.append(date)
        time_match = re.fullmatch(r"(\d{1,2}:\d{2} [AP]M)\s*[-\u2013\u2014]\s*(\d{1,2}:\d{2} [AP]M)", time_text)
        start = datetime.combine(date.date(), datetime.strptime(time_match[1], "%I:%M %p").time(), VANCOUVER) if time_match else date
        end = datetime.combine(date.date(), datetime.strptime(time_match[2], "%I:%M %p").time(), VANCOUVER) if time_match else None
        title = heading.get_text(" ", strip=True)
        if not lower <= start < upper or EXCLUDED_TITLE.search(title):
            continue
        url = link.get("href", "")
        if urlsplit(url).hostname != "amsclubs.ca" or urlsplit(url).scheme != "https":
            raise ValueError("AMS listing has an unexpected source URL")
        description = card.select_one(".event-description")
        result.append(_listing(url, url, title, start, end, venue, organizers.get(name),
                               description.get_text(" ", strip=True) if description else "",
                               "free" if re.match(r"^free\b", title, re.I) else "unknown",
                               all_day=time_match is None))
    paging = soup.select_one("a.next-page")
    next_page = paging.get("href") if paging else None
    # Listing pages are chronological. Stop after a page reaches the end of the horizon.
    return result, next_page if dates and min(dates) < upper and max(dates) < upper else None


def _ams(client, url, now, days, options):
    events, seen, visited = [], set(), set()
    for _ in range(10):
        if url in visited:
            raise ValueError("AMS pagination repeats a page")
        visited.add(url)
        page, next_page = ams_page(download(client, url), now=now, days=days,
                                   organizers=options.get("organizers"))
        for event in page:
            if event["external_id"] not in seen:
                events.append(event)
                seen.add(event["external_id"])
        if not next_page:
            return events
        next_url = urljoin(url, next_page)
        parsed = urlsplit(next_url)
        path = re.sub(r"/+", "/", parsed.path)
        if parsed.scheme != "https" or parsed.hostname != "amsclubs.ca" or not re.fullmatch(r"/all-events/pagenum/\d+/", path):
            raise ValueError("AMS pagination must stay on the public events listing")
        url = "https://amsclubs.ca" + path
    raise ValueError("AMS pagination limit reached; shorten the lookahead")


def _tribe(client, url, now, days, options):
    lower, upper = _window(now, days)
    events = []
    for page in range(1, 5):
        endpoint = httpx.URL(url).copy_merge_params({
            "start_date": lower.strftime("%Y-%m-%d %H:%M:%S"),
            "end_date": upper.strftime("%Y-%m-%d %H:%M:%S"), "per_page": 50, "page": page,
        })
        data = json.loads(download(client, str(endpoint)))
        if not isinstance(data.get("events"), list):
            raise ValueError("Expected an Events Calendar events array")
        for event in data["events"]:
            if event.get("status") != "publish" or event.get("hide_from_listings"):
                continue
            zone = event.get("timezone", "America/Vancouver")
            if zone != "America/Vancouver":
                raise ValueError("Unexpected calendar timezone")
            start = datetime.fromisoformat(event["start_date"]).replace(tzinfo=VANCOUVER)
            end = datetime.fromisoformat(event["end_date"]).replace(tzinfo=VANCOUVER) if event.get("end_date") else None
            title = plain_text(event["title"])
            if not lower <= start < upper or EXCLUDED_TITLE.search(title):
                continue
            organizer = next((options.get("organizers", {}).get(o.get("slug"))
                              for o in event.get("organizer", [])
                              if o.get("slug") in options.get("organizers", {})), None)
            venue = event.get("venue") or {}
            source_url = event["url"]
            if urlsplit(source_url).hostname != urlsplit(url).hostname:
                raise ValueError("Unexpected event source origin")
            events.append(_listing(str(event["id"]), source_url, title, start, end,
                                   plain_text(venue.get("venue")), organizer,
                                   plain_text(event.get("description")),
                                   "free" if str(event.get("cost", "")).casefold() in ("free", "0", "$0") else "unknown",
                                   all_day=event.get("all_day", False)))
        if page >= int(data.get("total_pages", 1)):
            return events
    raise ValueError("Calendar pagination limit reached; shorten the lookahead")


def _rss(client, url):
    root = ET.fromstring(download(client, url))
    if root.tag != "rss":
        raise ValueError("Expected an RSS feed")
    events = []
    for item in root.findall("./channel/item"):
        title = plain_text(item.findtext("title"))
        # Continuing clinical education is outside this student-events pilot.
        if not title or re.search(r"\bUBC CPD\b", title, re.I):
            continue
        link = item.findtext("link", "")
        if urlsplit(link).hostname != urlsplit(url).hostname or urlsplit(link).scheme != "https":
            raise ValueError("RSS item has an unexpected source origin")
        # pubDate is a publication timestamp, never infer an event date from it.
        events.append(_listing(item.findtext("guid") or link, link, title,
                               description=plain_text(item.findtext("description"))))
    return events


def _luma(client, url, now, days, options):
    lower, upper = _window(now, days)
    soup = BeautifulSoup(download(client, url), "html.parser")
    node = soup.find("script", id="__NEXT_DATA__")
    if node is None:
        raise ValueError("Luma public calendar format changed")
    data = json.loads(node.get_text())["props"]["pageProps"]["initialData"]["data"]
    upcoming = data["upcoming"]
    if upcoming.get("has_more"):
        raise ValueError("Luma has more events than its public page provides")
    events = []
    for entry in upcoming["entries"]:
        event = entry["event"]
        start = datetime.fromisoformat(event["start_at"].replace("Z", "+00:00")).astimezone(VANCOUVER)
        end = datetime.fromisoformat(event["end_at"].replace("Z", "+00:00")).astimezone(VANCOUVER) if event.get("end_at") else None
        if not lower <= start < upper:
            continue
        slug = event["url"]
        source_url = slug if slug.startswith("https://luma.com/") else "https://luma.com/" + slug
        address = event.get("geo_address_json") or {}
        venue = address.get("address") if isinstance(address, dict) else None
        events.append(_listing(event["api_id"], source_url, event["name"], start, end,
                               venue, options.get("organizer_slug")))
    return events


def _html_events(client, url, now, days, options):
    """Capture linked announcements for review without inventing dates from posting times."""
    soup = BeautifulSoup(download(client, url), "html.parser")
    events, seen = [], set()
    pattern = options.get("event_path", r"/events?/[^/?#]+")
    for link in soup.select("a[href]"):
        target = urljoin(url, link["href"]).split("#")[0]
        title = link.get_text(" ", strip=True)
        if (urlsplit(target).hostname != urlsplit(url).hostname or not re.search(pattern, urlsplit(target).path)
                or not 5 <= len(title) <= 300 or target in seen):
            continue
        seen.add(target)
        context = link.parent.get_text(" ", strip=True)[:5000]
        events.append(_listing(target, target, title, organizer=options.get("organizer_slug"),
                               description=context))
    if not events:
        raise ValueError("No readable event links; source needs inspection")
    return events


def _biztech(client, url, now, days, options):
    lower, upper = _window(now, days)
    soup = BeautifulSoup(download(client, url), "html.parser")
    cards = soup.select('[data-framer-name="ContentArea"]')
    events, seen = [], set()
    for card in cards:
        texts = [p.get_text(" ", strip=True) for p in card.select("p")]
        match = next((re.fullmatch(r"([A-Za-z]+) (\d{1,2})(?:[-\u2013](\d{1,2}))?, (\d{4})", t)
                      for t in texts if re.fullmatch(r"([A-Za-z]+) (\d{1,2})(?:[-\u2013](\d{1,2}))?, (\d{4})", t)), None)
        if not match:
            continue
        start = datetime.strptime(f"{match[1]} {match[2]}, {match[4]}", "%B %d, %Y").replace(tzinfo=VANCOUVER)
        index = texts.index(match[0])
        if index + 1 >= len(texts):
            raise ValueError("BizTech event title is missing")
        title = texts[index + 1]
        if not lower.date() <= start.date() < upper.date() or title in seen:
            continue
        seen.add(title)
        detail = next((urljoin(url, a["href"]) for a in card.select("a[href]")
                       if "/events/" in urljoin(url, a["href"])), url + "#" + re.sub(r"\W+", "-", title.lower()))
        events.append(_listing(title, detail, title, start=start,
                               organizer=options.get("organizer_slug", "ubc-biztech"),
                               description="\n".join(texts), all_day=True))
    if not cards:
        raise ValueError("BizTech event page format changed")
    return events


def public_feed(client, url, feed_format, *, now=None, days=60, options=None):
    options = options or {}
    try:
        if feed_format == "ams_html":
            events = _ams(client, url, now, days, options)
        elif feed_format == "tribe":
            events = _tribe(client, url, now, days, options)
        elif feed_format == "rss":
            events = _rss(client, url)
        elif feed_format == "luma":
            events = _luma(client, url, now, days, options)
        elif feed_format == "html_events":
            events = _html_events(client, url, now, days, options)
        elif feed_format == "biztech":
            events = _biztech(client, url, now, days, options)
        else:
            raise ValueError("Unknown public-source adapter")
    except (KeyError, TypeError, AttributeError, ET.ParseError) as exc:
        raise ValueError("Public source response format changed") from exc
    if len(events) > 50:
        raise ValueError("More than 50 source listings; shorten the lookahead")
    return {"events": events}
