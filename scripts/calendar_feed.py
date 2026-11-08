"""Convert the public CSSS affiliate iCalendar into stable, structured intake records."""

import hashlib
import html
import re
from datetime import date, datetime, time, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from icalendar import Calendar
import recurring_ical_events

CSSS_FEED_URL = (
    "https://calendar.google.com/calendar/ical/"
    "1e1ce102f2951b154df282dc66ea69722b37b41a8956d88361befe9ceb9e8080"
    "%40group.calendar.google.com/public/basic.ics"
)
CSSS_PAGE_URL = "https://ubccsss.org/about/affiliates/"
CSSS_SOURCE_ID = "src-csss-affiliates"
VANCOUVER = ZoneInfo("America/Vancouver")
CLUBS = (
    ("ubc-csss", "UBC Computer Science Student Society", ("CSSS",)),
    ("ubc-wics", "UBC Women in Computer Science", ("WiCS",)),
    ("ubc-nwplus", "nwPlus", ("nwPlus",)),
    ("ubc-wids", "UBC Women in Data Science", ("WiDS",)),
)
EXCLUDED_TITLE = re.compile(
    r"\b(?:hold|tentative|reading\s+(?:break|week)|academic\s+break|"
    r"(?:weekly\s+)?planning\s+meeting|(?:weekly\s+)?tcf\s+meeting|internal\s+meeting|executive\s+meeting|"
    r"exec\s+meeting|board\s+meeting|statutory\s+holiday)\b",
    re.IGNORECASE,
)


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p", "div", "li"):
            self.parts.append("\n")
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value and urlsplit(value).scheme in ("http", "https"):
                    self.parts.append(f" {value} ")

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value) -> str:
    parser = _PlainText()
    parser.feed(str(value or ""))
    return html.unescape("".join(parser.parts)).strip()


def _instant(value: date | datetime) -> datetime:
    if not isinstance(value, datetime):
        return datetime.combine(value, time.min, VANCOUVER)
    return value.replace(tzinfo=VANCOUVER) if value.tzinfo is None else value.astimezone(VANCOUVER)


def _identity(value: date | datetime) -> str:
    return value.astimezone(timezone.utc).isoformat() if isinstance(value, datetime) else value.isoformat()


def _organizer(title: str, organizer) -> str | None:
    explicit = str(organizer.params.get("CN", "")) if organizer is not None else ""
    for club_id, name, aliases in CLUBS:
        if explicit.casefold() in {name.casefold(), *(alias.casefold() for alias in aliases)}:
            return club_id
    matches = []
    for club_id, _, aliases in CLUBS:
        for alias in aliases:
            match = re.search(r"\b" + re.escape(alias) + r"\b", title, re.IGNORECASE)
            if match:
                matches.append((match.start(), club_id))
    return min(matches)[1] if matches else None


def calendar_feed(data: bytes, *, now: datetime | None = None, days: int = 60) -> dict:
    """Expand a bounded horizon; preserve UID/RECURRENCE-ID across changed times and venues."""
    if not 1 <= days <= 180:
        raise ValueError("Calendar lookahead must be between 1 and 180 days")
    start = (now or datetime.now(timezone.utc)).astimezone(VANCOUVER)
    end = start + timedelta(days=days)
    calendar = Calendar.from_ical(data)
    if calendar.name != "VCALENDAR":
        raise ValueError("Expected a VCALENDAR")
    recurring_uids = {
        str(event.get("UID", "")) for event in calendar.walk("VEVENT")
        if any(key in event for key in ("RRULE", "RDATE", "RECURRENCE-ID"))
    }
    # Expanding minute/second recurrence rules is inappropriate for this event feed.
    for event in calendar.walk("VEVENT"):
        rule = event.get("RRULE", {})
        if any(str(freq).upper() in ("SECONDLY", "MINUTELY") for freq in rule.get("FREQ", [])):
            raise ValueError("Calendar recurrence is too frequent")
    occurrences = recurring_ical_events.of(calendar, keep_recurrence_attributes=True).between(start, end)
    listings = []
    for event in occurrences:
        title = plain_text(event.get("SUMMARY"))
        status = str(event.get("STATUS", "CONFIRMED")).upper()
        if not title or EXCLUDED_TITLE.search(title) or status in ("CANCELLED", "TENTATIVE"):
            continue
        uid = str(event.get("UID", ""))
        if not uid or "DTSTART" not in event:
            raise ValueError("Calendar event requires UID and DTSTART")
        raw_start = event.decoded("DTSTART")
        local_start = _instant(raw_start)
        # between() also returns events overlapping the window; this checker imports future starts.
        if isinstance(raw_start, datetime):
            if not start <= local_start < end:
                continue
        elif not start.date() <= raw_start < end.date():
            continue
        raw_end = event.decoded("DTEND") if "DTEND" in event else None
        local_end = _instant(raw_end) if raw_end is not None else None
        occurrence = "single"
        if uid in recurring_uids:
            recurrence = event.decoded("RECURRENCE-ID") if "RECURRENCE-ID" in event else raw_start
            occurrence = _identity(_instant(recurrence)) if isinstance(recurrence, datetime) else _identity(recurrence)
        external_id = "ical:" + hashlib.sha256(f"{uid}\n{occurrence}".encode()).hexdigest()
        venue = plain_text(event.get("LOCATION")) or None
        description = plain_text(event.get("DESCRIPTION"))
        url = str(event.get("URL", ""))
        parsed_url = urlsplit(url)
        source_url = url if parsed_url.scheme in ("https", "http") and parsed_url.hostname else CSSS_PAGE_URL
        timed = isinstance(raw_start, datetime)
        candidate = {
            "organizer_slug": _organizer(title, event.get("ORGANIZER")),
            "title": title,
            "local_date": local_start.date().isoformat(),
            "local_start": local_start.strftime("%H:%M") if timed else None,
            "local_end": local_end.strftime("%H:%M") if timed and isinstance(raw_end, datetime)
            and local_end.date() == local_start.date() else None,
            "timezone": "America/Vancouver",
            "venue": venue,
            "cost_status": "unknown",
            "beginner_friendly": None,
            "topics": [],
            "rsvp_url": None,
        }
        # No polling timestamps or LAST-MODIFIED: an unchanged event must hash identically.
        caption = "\n".join(filter(None, (
            f"Calendar: {plain_text(calendar.get('X-WR-CALNAME')) or 'CSSS affiliate calendar'}",
            f"Title: {title}",
            f"Date: {candidate['local_date']}",
            f"Start: {candidate['local_start'] or 'not listed'} (America/Vancouver)",
            f"End: {local_end.isoformat()}" if local_end else None,
            f"Venue: {venue}" if venue else None,
            f"Description: {description}" if description else None,
        )))
        listings.append({
            "external_id": external_id, "source_url": source_url, "caption": caption,
            "candidate": candidate,
        })
    listings.sort(key=lambda item: (item["candidate"]["local_date"], item["candidate"]["local_start"] or "", item["external_id"]))
    if len(listings) > 50:
        raise ValueError("More than 50 upcoming listings; reduce the calendar lookahead")
    return {"events": listings}
