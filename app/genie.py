"""Recommend real Quad events, with Databricks Genie ranking the eligible listings."""
import json
import logging
import re
import time
from datetime import datetime, timedelta
from threading import BoundedSemaphore

import httpx

from . import config, databricks, service
from .topics import TOPICS

logger = logging.getLogger(__name__)
_in_flight = BoundedSemaphore(2)
_event_id = re.compile(r"evt-[a-z0-9]{1,40}")
_ai = r"\b(?:ai|artificial intelligence|machine learning|deep learning|neural networks?|generative ai|llms?)\b"
_running = r"\b(?:running|jog(?:ging)?|runners?|(?:fun|club|group|trail|social|morning|evening) runs?|marathons?|(?:5|10|21|42)\s*k)\b"
_stopwords = set("""
    a about after all am and any around at be before can could different do event events find for
    from get give going happening help how i id im in interested is it join learn learning looking
    me more my near of on one ones only organizers out please recommend show some something that
    the there things this to try trying ubc upcoming want week whats what where which with would
    today tonight tomorrow weekend next free beginner friendly beginners class evening evenings
    campus new hobby club clubs organizer easy start intro no experience first time who are
    go attend workshop workshops session sessions list cost pm
""".split())
_numbers = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _candidates(conn, question, now):
    q = question.casefold().replace("’", "'")
    today = now.date()
    start, end = today, None
    if "tomorrow" in q:
        start = end = today + timedelta(days=1)
    elif "weekend" in q:
        if today.weekday() == 6 and "next weekend" not in q:
            end = start
        else:
            days_until = (5 - today.weekday()) % 7
            start += timedelta(days=days_until or (7 if "next weekend" in q else 0))
            end = start + timedelta(days=1)
    elif "next week" in q:
        start = today + timedelta(days=7 - today.weekday())
        end = start + timedelta(days=6)
    elif "this week" in q:
        end = today + timedelta(days=6)
    elif re.search(r"\b(?:today|tonight)\b", q):
        end = today

    limit_match = re.search(
        r"\b(?:give me|show(?: me)?|find|suggest|recommend|top)\s+(?:the\s+)?(\d{1,3}|"
        + "|".join(_numbers) + r")\b", q,
    )
    limit = 3
    if limit_match:
        number = limit_match[1]
        limit = min(5, max(1, int(number) if number.isdigit() else _numbers[number]))
    free = bool(re.search(r"\b(?:free|no cost)\b", q))
    beginner = bool(re.search(r"\b(?:beginners?|beginner-friendly|no experience)\b", q))
    learning = bool(re.search(r"\b(?:learn|learning|intro|getting started)\b", q))
    after_four = bool(re.search(r"\b(?:after class|after 4(?::00)?(?:\s*p\.?m\.?)?|evenings?|tonight)\b", q))
    diverse = bool(re.search(r"\b(?:different|distinct) (?:clubs|organizers)\b", q))

    specialty = None
    if re.search(r"\b(?:running|jogging|jog|runners?|runs?|marathons?|(?:5|10)\s*k)\b", q):
        specialty = _running
    elif re.search(_ai, q):
        specialty = _ai
    topics = set(re.findall(r"[a-z]+", q)) & set(TOPICS)
    keywords = set(re.findall(r"[a-z]{2,}", q)) - _stopwords - _numbers.keys() - topics
    rows = conn.execute("""
        SELECT e.event_id, e.club_id, c.display_name AS club_name, e.title, e.venue, e.local_date,
               e.local_start, e.cost_status, e.beginner_friendly, e.topics, min(a.source_url) AS source_url
        FROM events e JOIN clubs c USING (club_id)
        JOIN source_announcements a ON a.event_id=e.event_id
          AND a.status='linked' AND a.source_url LIKE 'https://%' AND a.source_id<>'src-demo-feed'
        WHERE e.state='published' AND e.local_date BETWEEN ? AND ?
          AND (e.local_date > ? OR e.local_start IS NULL OR e.local_start >= ?)
          AND (? = 0 OR e.cost_status = 'free')
          AND (? = 0 OR e.beginner_friendly = 1)
          AND (? = 0 OR e.local_start >= '16:00')
        GROUP BY e.event_id
        ORDER BY e.local_date, e.local_start IS NULL, e.local_start, e.event_id
        """, (start.isoformat(), end.isoformat() if end else "9999-12-31",
              today.isoformat(), now.strftime("%H:%M"), free, beginner, after_four))
    ranked = []
    for row in rows:
        event = dict(row)
        if not _event_id.fullmatch(event["event_id"]):
            continue
        text = f'{event["title"]} {event["club_name"]}'.casefold()
        if specialty and not re.search(specialty, text):
            continue
        if not specialty and topics and not topics.intersection(json.loads(event["topics"])):
            continue
        keyword_matches = len(keywords.intersection(re.findall(r"[a-z]+", text)))
        if not specialty and keywords and not keyword_matches:
            continue
        introductory = event["beginner_friendly"] or re.search(r"\b(?:intro|introduction|basics)\b", text)
        ranked.append((keyword_matches + 2 * bool(learning and introductory), event))
    ranked.sort(key=lambda entry: -entry[0])
    candidates = [event for _, event in ranked]
    if diverse:
        by_club = {}
        for event in candidates:
            by_club.setdefault(event["club_id"], event)
        candidates = list(by_club.values())
    return candidates, limit, learning


def _reserve_request(conn, day):
    limit = int(config.get("GENIE_DAILY_LIMIT", "30"))
    if limit <= 0:
        return False
    with conn:
        return conn.execute("""
            INSERT INTO genie_usage (day, requests) VALUES (?, 1)
            ON CONFLICT(day) DO UPDATE SET requests=requests+1 WHERE requests < ?
            """, (day, limit)).rowcount == 1


def _genie_order(space, ids, limit, learning, today):
    base = f"/api/2.0/genie/spaces/{space}"
    prompt = (
        f"Recommend up to {limit} published upcoming UBC events on or after {today} Vancouver time. "
        f"Consider only these event IDs: {', '.join(ids)}. "
        "Filter with WHERE event_id IN (...) and include event_id in the SQL result. "
        + ("Prefer introductory workshops, then earliest dates." if learning else "Prefer the earliest dates.")
    )
    deadline = time.monotonic() + 30
    with databricks._client(timeout=5) as client:
        data = client.post(f"{base}/start-conversation", json={"content": prompt}).raise_for_status().json()
        message = data["message"]
        path = f'{base}/conversations/{data["conversation_id"]}/messages/{data["message_id"]}'
        while message["status"] not in {"COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"}:
            if time.monotonic() >= deadline:
                return []
            time.sleep(1)
            message = client.get(path).raise_for_status().json()
        if message["status"] != "COMPLETED":
            return []
        for attachment in message.get("attachments", []):
            if not attachment.get("query"):
                continue
            data = client.get(f'{path}/attachments/{attachment["attachment_id"]}/query-result')
            statement = data.raise_for_status().json()["statement_response"]
            columns = [c["name"].lower() for c in statement["manifest"]["schema"]["columns"]]
            if "event_id" in columns:
                index = columns.index("event_id")
                return [row[index] for row in statement["result"].get("data_array", [])]
    return []


def recommend(conn, question):
    now = datetime.now(service.VAN)
    today = now.date().isoformat()
    candidates, limit, learning = _candidates(conn, question, now)
    engine = "quad"
    space = config.get("GENIE_SPACE_ID")
    if candidates and re.fullmatch(r"[0-9a-f]{32}", space) and databricks.configured():
        eligible = {event["event_id"]: event for event in candidates[:30]}
        if _in_flight.acquire(blocking=False):
            try:
                if _reserve_request(conn, today):
                    order = _genie_order(space, list(eligible), limit, learning, today)
                    ranked = [eligible[event_id] for event_id in dict.fromkeys(order) if event_id in eligible]
                    if ranked:
                        seen = {event["event_id"] for event in ranked}
                        candidates = ranked + [event for event in candidates if event["event_id"] not in seen]
                        engine = "genie"
            except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
                logger.warning("Genie unavailable (%s)", type(exc).__name__)
            finally:
                _in_flight.release()
    return {
        "engine": engine,
        "requested": limit,
        "matched": len(candidates),
        "events": [{key: value for key, value in event.items() if key not in {"topics", "club_id"}}
                   for event in candidates[:limit]],
    }
