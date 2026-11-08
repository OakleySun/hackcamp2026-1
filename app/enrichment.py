"""Publish confirmed calendar matches and retain uncertain ones in the review inbox."""

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from . import matching, service, topics
from .models import Candidate, Evidence

SOURCES = ("src-ubc-events-home", "src-ubc-events-rss")
FIELDS = ("local_date", "local_start", "local_end", "venue", "cost_status")
OPEN = """FROM review_items r JOIN source_announcements a USING (announcement_id)
          WHERE r.state='open' AND a.source_id IN (?, ?)"""


class Finding(BaseModel):
    url: str = Field(max_length=2048)
    title: str = Field(min_length=1, max_length=300)
    organizer: str | None = Field(default=None, min_length=1, max_length=240)
    local_date: date
    local_start: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    local_end: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    venue: str | None = Field(default=None, max_length=300)
    cost_status: Literal["free", "paid", "unknown"] = "unknown"


class Result(BaseModel):
    review_id: str = Field(max_length=64)
    finding: Finding | None


class Batch(BaseModel):
    results: list[Result] = Field(max_length=200)


class Approval(BaseModel):
    version: str = Field(pattern=r"^[a-f0-9]{64}$")


def event_url(url):
    parts = urlsplit(url or "")
    if parts.scheme == "https" and parts.netloc == "events.ubc.ca" and not parts.query:
        path = parts.path.rstrip("/")
        if path.startswith("/event/"):
            return f"https://events.ubc.ca{path}"
    return None


def work(conn):
    seen = set()
    items = []
    for row in conn.execute("SELECT r.review_id, a.source_url, a.candidate " + OPEN +
                            " ORDER BY r.created_at DESC, r.review_id", SOURCES):
        url = event_url(row["source_url"])
        candidate = json.loads(row["candidate"] or "{}")
        if candidate.get("local_date") and candidate.get("organizer_slug"):
            continue
        title = candidate.get("title")
        key = (url, matching.norm_title(title))
        if url and key[1] and key not in seen:
            seen.add(key)
            items.append({"review_id": row["review_id"], "url": url, "title": title})
            if len(items) == 200:
                break
    return items


def store(conn, batch):
    saved = {}
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        open_items = {item["review_id"]: item for item in work(conn)}
        for result in batch.results:
            item = open_items.get(result.review_id)
            if item is None:
                continue
            finding = result.finding
            if finding is None:
                conn.execute("DELETE FROM review_enrichments WHERE review_id=?", (result.review_id,))
                saved.pop(result.review_id, None)
                continue
            if event_url(finding.url) != item["url"] or matching.norm_title(finding.title) != matching.norm_title(item["title"]):
                raise ValueError("Evidence must identify the original event occurrence")
            evidence = finding.model_dump_json()
            version = hashlib.sha256(evidence.encode()).hexdigest()
            conn.execute("""INSERT INTO review_enrichments(review_id,evidence,version,checked_at) VALUES(?,?,?,?)
                         ON CONFLICT(review_id) DO UPDATE SET evidence=excluded.evidence,
                         version=excluded.version, checked_at=excluded.checked_at""",
                         (result.review_id, evidence, version, service.now()))
            saved[result.review_id] = (version, finding.organizer)

    counts = {"suggestions": len(saved), "published": 0, "linked": 0, "unresolved": 0}
    for review_id, (version, organizer) in saved.items():
        if not organizer:
            counts["unresolved"] += 1
            continue
        try:
            result = approve(conn, review_id, version, reviewer="official calendar enrichment")
        except (service.ReviewConflict, ValueError):
            counts["unresolved"] += 1
        else:
            counts["published" if result["outcome"] == "new" else "linked"] += 1
    return counts


def inbox(conn):
    rows = conn.execute("""SELECT r.review_id, a.source_url, a.candidate, e.evidence, e.version, e.checked_at
                            FROM review_enrichments e JOIN review_items r USING (review_id)
                            JOIN source_announcements a USING (announcement_id)
                            WHERE r.state='open' ORDER BY e.checked_at DESC""")
    current = {item["review_id"] for item in work(conn)}
    return [{**dict(row), "candidate": json.loads(row["candidate"] or "{}"), "evidence": json.loads(row["evidence"])}
            for row in rows if row["review_id"] in current]


def approve(conn, review_id, version, reviewer="enrichment review"):
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        record = conn.execute("""SELECT r.state, a.announcement_id, a.source_url, a.candidate, a.caption,
            e.version, e.evidence, e.checked_at FROM review_items r
            JOIN source_announcements a USING (announcement_id)
            JOIN review_enrichments e USING (review_id) WHERE r.review_id=?""", (review_id,)).fetchone()
        if not record or record["state"] != "open" or record["version"] != version:
            raise service.ReviewConflict("The suggestion changed or was already reviewed. Reload the inbox.")
        if datetime.fromisoformat(record["checked_at"]) < datetime.fromisoformat(service.now()) - timedelta(days=2):
            raise service.ReviewConflict("The source needs to be checked again before approval.")
        finding = Finding.model_validate_json(record["evidence"])
        if finding.local_date < datetime.now(service.VAN).date() or not finding.organizer:
            raise ValueError("An upcoming date and named organizer are required to approve.")
        candidate = Candidate.model_validate_json(record["candidate"])
        candidate.topics = topics.event_topics(candidate.topics, candidate.title, (record["caption"],))
        values = finding.model_dump(mode="json")
        for field in FIELDS:
            previous = getattr(candidate, field)
            suggested = values[field]
            if previous not in (None, "unknown") and suggested not in (None, "unknown", previous):
                raise service.ReviewConflict("The original and suggested details disagree. Leave this item for manual review.")
        club = service.resolve_club(conn, finding.organizer)
        original_club = service.resolve_club(conn, candidate.organizer_slug)
        if candidate.organizer_slug and original_club != club:
            raise service.ReviewConflict("The organizers disagree. Leave this item for manual review.")
        if club is None:
            slug = re.sub(r"[^a-z0-9]+", "-", finding.organizer.lower()).strip("-")[:70]
            club = f"ubc-events-{slug}"
            conn.execute("INSERT INTO clubs(club_id,display_name,aliases) VALUES(?,?,'[]') ON CONFLICT DO NOTHING",
                         (club, finding.organizer))
            if conn.execute("SELECT display_name FROM clubs WHERE club_id=?", (club,)).fetchone()[0] != finding.organizer:
                raise service.ReviewConflict("The organizer needs to be matched manually.")

        updates = {"organizer_slug": club}
        for field in FIELDS:
            if getattr(candidate, field) in (None, "unknown") and values[field] not in (None, "unknown"):
                updates[field] = values[field]
        evidence = {field: f"{finding.url} — {finding.organizer if field == 'organizer_slug' else value}"
                    for field, value in updates.items()}
        candidate = candidate.model_copy(update={**updates, "evidence": [*candidate.evidence,
            *(Evidence(field=field, excerpt=excerpt) for field, excerpt in evidence.items())]})

        same_url = conn.execute("""SELECT DISTINCT a.event_id FROM source_announcements a
            JOIN events e USING(event_id) WHERE rtrim(a.source_url,'/')=? AND e.state='published'""",
            (event_url(finding.url),)).fetchall()
        events = [service.get_event(conn, row["event_id"]) for row in conn.execute(
            "SELECT event_id FROM events WHERE club_id=? AND state='published'", (club,))]
        if same_url:
            if len(same_url) != 1:
                raise service.ReviewConflict("More than one published event uses this source link.")
            match = service.get_event(conn, same_url[0]["event_id"])
            if match["local_date"] != candidate.local_date or matching.norm_title(match["title"]) != matching.norm_title(candidate.title):
                raise service.ReviewConflict("An existing event uses this link with a different title or date.")
            decision = matching.decide([match], candidate, match["event_id"])
        else:
            decision = matching.decide(events, candidate)
        if decision["kind"] == "review":
            raise service.ReviewConflict("A possible duplicate needs manual review: " + decision["reason"])

        event_id = decision["event_id"]
        duplicates = conn.execute("SELECT r.review_id, a.announcement_id, a.candidate, a.caption " + OPEN +
                                  " AND rtrim(a.source_url,'/')=? ORDER BY r.review_id<>?",
                                  (*SOURCES, event_url(finding.url), review_id)).fetchall()
        for row in duplicates:
            original = json.loads(row["candidate"] or "{}")
            if matching.norm_title(original.get("title")) != matching.norm_title(candidate.title):
                continue
            if any(original.get(field) not in (None, "unknown", getattr(candidate, field)) for field in FIELDS):
                continue
            if original.get("organizer_slug") and service.resolve_club(conn, original["organizer_slug"]) != club:
                continue
            aid = row["announcement_id"]
            updated = Candidate.model_validate(original)
            updated = updated.model_copy(update={**updates, "evidence": [*updated.evidence,
                *(Evidence(field=field, excerpt=excerpt) for field, excerpt in evidence.items())]})
            updated.topics = topics.event_topics(updated.topics, updated.title, (row["caption"],))
            conn.execute("UPDATE source_announcements SET candidate=?,evidence=?,error=NULL WHERE announcement_id=?",
                         (updated.model_dump_json(), json.dumps(evidence), aid))
            if event_id is None:
                event_id = service.create_event(conn, club, candidate, aid, reviewer)
                state = "separate"
            else:
                current = service.get_event(conn, event_id)
                if not current["topics"] and updated.topics:
                    service.update_event(conn, event_id, {"topics": updated.topics}, "topics from verified source")
                conn.execute("UPDATE source_announcements SET event_id=?,status='linked' WHERE announcement_id=?",
                             (event_id, aid))
                service.enqueue_announcement(conn, aid)
                state = "linked"
            conn.execute("UPDATE review_items SET state=?,reviewer=?,resolved_at=? WHERE review_id=?",
                         (state, reviewer, service.now(), row["review_id"]))
    return {"event_id": event_id, "outcome": decision["kind"]}
