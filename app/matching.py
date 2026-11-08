"""Decide whether an incoming candidate is a new event, a mirror of one, or needs review."""
from __future__ import annotations

import difflib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

from .models import Candidate

TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "igshid", "gclid"}
CONFLICT_FIELDS = ("local_date", "local_start", "venue")
FILL_FIELDS = ("local_start", "local_end", "venue", "rsvp_url")


def norm_title(title: str | None) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (title or "").lower()).strip()


def norm_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def rsvp_key(url: str | None) -> str | None:
    """Canonical event link: lowercase host, no scheme, fragment or tracking parameters."""
    if not url:
        return None
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = [(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in TRACKING]
    key = host + parts.path.rstrip("/").lower()
    return key + ("?" + urlencode(sorted(query)) if query else "")


def is_specific_rsvp(url: str | None) -> bool:
    """A link names one event if its path has 2+ segments or an identifying query.
    A bare general sign-up page such as example.org/signup is not specific."""
    if not url:
        return False
    parts = urlsplit(url.strip())
    segments = [s for s in parts.path.split("/") if s]
    return len(segments) >= 2 or bool(parse_qsl(parts.query))


def _diff(event: dict, c: Candidate) -> tuple[dict, dict]:
    conflicts, fills = {}, {}
    for f in CONFLICT_FIELDS:
        new, old = getattr(c, f), event[f]
        if new is not None and old is not None and norm_text(str(new)) != norm_text(str(old)):
            conflicts[f] = {"old": old, "new": new}
        elif new is not None and old is None:
            fills[f] = new
    for f in FILL_FIELDS:
        new, old = getattr(c, f), event[f]
        if new is not None and old is None and f not in fills:
            fills[f] = new
    if event["cost_status"] == "unknown" and c.cost_status != "unknown":
        fills["cost_status"] = c.cost_status
    if event["beginner_friendly"] is None and c.beginner_friendly is not None:
        fills["beginner_friendly"] = int(c.beginner_friendly)
    return conflicts, fills


def decide(events: list[dict], c: Candidate, prior_event_id: str | None = None) -> dict:
    """events: published events for the candidate's club.
    Returns {"kind": "new"|"link"|"review", "event_id", "candidate_ids", "conflicts", "fills", "reason"}."""
    if prior_event_id:
        cands = [e for e in events if e["event_id"] == prior_event_id]
    else:
        cands = []
        key = rsvp_key(c.rsvp_url)
        if key and is_specific_rsvp(c.rsvp_url):
            cands = [e for e in events if rsvp_key(e["rsvp_url"]) == key]
        if not cands:
            cands = [e for e in events
                     if norm_title(e["title"]) == norm_title(c.title) and e["local_date"] == c.local_date]
        if not cands:
            near = [e for e in events if e["local_date"] == c.local_date and
                    difflib.SequenceMatcher(None, norm_title(e["title"]), norm_title(c.title)).ratio() >= 0.8]
            if near:
                return {"kind": "review", "event_id": None, "reason": "similar title, not an exact match",
                        "candidate_ids": [e["event_id"] for e in near], "conflicts": {}, "fills": {}}
    if not cands:
        return {"kind": "new", "event_id": None, "candidate_ids": [], "conflicts": {}, "fills": {}, "reason": None}
    if len(cands) > 1:
        return {"kind": "review", "event_id": None, "reason": "multiple candidate events",
                "candidate_ids": [e["event_id"] for e in cands], "conflicts": {}, "fills": {}}
    e = cands[0]
    conflicts, fills = _diff(e, c)
    if conflicts:
        return {"kind": "review", "event_id": e["event_id"], "reason": "conflicting " + ", ".join(conflicts),
                "candidate_ids": [e["event_id"]], "conflicts": conflicts, "fills": fills}
    return {"kind": "link", "event_id": e["event_id"], "candidate_ids": [e["event_id"]],
            "conflicts": {}, "fills": fills, "reason": None}
