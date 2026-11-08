"""Core business logic: intake, matching, review, revisions, outbox and delivery claims.

Every state change that must stay consistent (event revision + outbox row) happens inside one
`with conn:` block, which SQLite commits or rolls back as a unit.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config, matching, places, topics
from .extract import extract
from .models import Candidate

VAN = ZoneInfo("America/Vancouver")
SNAP_FIELDS = ("title", "local_date", "local_start", "local_end", "venue",
               "cost_status", "beginner_friendly", "topics", "perks", "audience", "rsvp_url")
JSON_FIELDS = ("topics", "perks", "audience")
CORRECTION_FIELDS = ("local_date", "local_start", "venue")
LEASE_SECONDS = 120


class ReviewConflict(Exception):
    """Raised for stale or already-resolved reviews (HTTP 409)."""


class NotFound(Exception):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def start_utc(date: str | None, start: str | None) -> str | None:
    if not date or not start:
        return None
    local = datetime.strptime(f"{date} {start}", "%Y-%m-%d %H:%M").replace(tzinfo=VAN)
    return local.astimezone(timezone.utc).isoformat(timespec="minutes")


# ---------------------------------------------------------------- Databricks export queue
# These only INSERT local rows; they must be called inside the caller's write transaction so the
# change and its export record commit together. The network call happens later in scripts/dbx_worker.py.

def _enqueue(conn, kind: str, aggregate: str, version: int, payload: dict) -> None:
    conn.execute("INSERT OR IGNORE INTO dbx_queue (op_key, kind, aggregate, version, payload, created_at, "
                 "next_retry_at) VALUES (?,?,?,?,?,?,?)",
                 (f"{kind}:{aggregate}:{version}", kind, aggregate, version, json.dumps(payload), now(), now()))


def enqueue_announcement(conn, aid: str) -> None:
    a = conn.execute("SELECT * FROM source_announcements WHERE announcement_id=?", (aid,)).fetchone()
    version = conn.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM dbx_queue "
                           "WHERE kind='announcement' AND aggregate=?", (aid,)).fetchone()[0]
    _enqueue(conn, "announcement", aid, version, {
        "announcement_id": aid, "source_id": a["source_id"], "external_id": a["external_id"],
        "source_url": a["source_url"], "detected_at": a["detected_at"], "status": a["status"],
        "caption": a["caption"], "candidate_json": a["candidate"], "evidence_json": a["evidence"],
        "event_id": a["event_id"], "projection_version": version})


def enqueue_revision(conn, event_id: str, revision: int) -> None:
    r = conn.execute("SELECT r.*, e.club_id FROM event_revisions r JOIN events e USING (event_id) "
                     "WHERE r.event_id=? AND r.revision=?", (event_id, revision)).fetchone()
    _enqueue(conn, "revision", event_id, revision, {
        "event_id": event_id, "revision": revision, "club_id": r["club_id"], "snapshot_json": r["snapshot"],
        "changed_json": r["changed"], "reason": r["reason"], "created_at": r["created_at"]})


def dbx_status(conn) -> dict:
    from . import databricks
    counts = {r["state"]: r["n"] for r in conn.execute("SELECT state, COUNT(*) AS n FROM dbx_queue GROUP BY state")}
    last = conn.execute("SELECT MAX(done_at) FROM dbx_queue WHERE state='done'").fetchone()[0]
    error = conn.execute("SELECT last_error FROM dbx_queue WHERE last_error IS NOT NULL AND state<>'done' "
                         "ORDER BY created_at DESC LIMIT 1").fetchone()
    return {"enabled": databricks.configured(), "pending": counts.get("pending", 0) + counts.get("claimed", 0),
            "failed": counts.get("failed", 0), "exported": counts.get("done", 0), "last_export_at": last,
            "last_error": error[0] if error else None}


# ---------------------------------------------------------------- events

def get_event(conn, event_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
    if not row:
        return None
    ev = dict(row)
    for f in JSON_FIELDS:
        ev[f] = json.loads(ev[f])
    return ev


def snapshot(ev: dict) -> dict:
    return {f: ev[f] for f in SNAP_FIELDS}


def eligible(ev: dict) -> bool:
    """An event can trigger alerts only with a known date and start time."""
    return bool(ev["local_date"] and ev["local_start"])


def _has_outbox(conn, event_id: str, kind: str) -> bool:
    return conn.execute("SELECT 1 FROM event_outbox WHERE event_id=? AND kind=?",
                        (event_id, kind)).fetchone() is not None


def create_event(conn, club_id: str, c: Candidate, ann_id: str, reviewer: str | None = None) -> str:
    eid = new_id("evt")
    conn.execute(
        """INSERT INTO events (event_id, club_id, title, local_date, local_start, local_end, start_utc,
                               venue, cost_status, beginner_friendly, topics, perks, audience, rsvp_url,
                               provenance)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (eid, club_id, c.title, c.local_date, c.local_start, c.local_end,
         start_utc(c.local_date, c.local_start), c.venue, c.cost_status,
         None if c.beginner_friendly is None else int(c.beginner_friendly),
         json.dumps(c.topics), json.dumps(c.perks), json.dumps(c.audience), c.rsvp_url, json.dumps({"created_from": ann_id})))
    ev = get_event(conn, eid)
    conn.execute("INSERT INTO event_revisions (event_id, revision, snapshot, changed, reason, approver, created_at) "
                 "VALUES (?,?,?,?,?,?,?)", (eid, 1, json.dumps(snapshot(ev)), "{}", "created", reviewer, now()))
    if eligible(ev):
        conn.execute("INSERT INTO event_outbox (event_id, revision, kind) VALUES (?,?,?)", (eid, 1, "new_event"))
    conn.execute("UPDATE source_announcements SET event_id=?, status='linked' WHERE announcement_id=?", (eid, ann_id))
    enqueue_revision(conn, eid, 1)
    enqueue_announcement(conn, ann_id)
    return eid


def update_event(conn, event_id: str, changes: dict, reason: str, approver: str | None = None) -> int:
    """Apply changes as a new revision. Returns the current revision (unchanged if nothing differs).
    Queues a `correction` for a confirmed date/time/venue change and `new_event` when an event
    first becomes alert-eligible."""
    ev = get_event(conn, event_id)
    changed = {f: {"old": ev[f], "new": v} for f, v in changes.items() if ev[f] != v}
    if not changed:
        return ev["current_revision"]
    rev = ev["current_revision"] + 1
    sets = ", ".join(f"{f}=?" for f in changed)
    conn.execute(f"UPDATE events SET {sets}, current_revision=? WHERE event_id=?",
                 [*[json.dumps(v["new"]) if f in JSON_FIELDS else v["new"] for f, v in changed.items()],
                  rev, event_id])
    updated = get_event(conn, event_id)
    conn.execute("UPDATE events SET start_utc=? WHERE event_id=?",
                 (start_utc(updated["local_date"], updated["local_start"]), event_id))
    conn.execute("INSERT INTO event_revisions (event_id, revision, snapshot, changed, reason, approver, created_at) "
                 "VALUES (?,?,?,?,?,?,?)",
                 (event_id, rev, json.dumps(snapshot(updated)), json.dumps(changed), reason, approver, now()))
    enqueue_revision(conn, event_id, rev)
    if changed.keys() == {"topics"}:
        # Tagging does not invalidate an already-open time/venue review.
        conn.execute("UPDATE review_items SET expected_revision=? WHERE state='open' AND expected_revision=? "
                     "AND json_extract(candidate_ids, '$[0]')=?", (rev, ev["current_revision"], event_id))
    material = any(f in CORRECTION_FIELDS and changed[f]["old"] is not None for f in changed)
    if material and _has_outbox(conn, event_id, "new_event"):
        conn.execute("INSERT INTO event_outbox (event_id, revision, kind) VALUES (?,?,?)",
                     (event_id, rev, "correction"))
    elif not eligible(ev) and eligible(updated) and not _has_outbox(conn, event_id, "new_event"):
        conn.execute("INSERT INTO event_outbox (event_id, revision, kind) VALUES (?,?,?)",
                     (event_id, rev, "new_event"))
    return rev


def backfill_event_topics(conn) -> int:
    """Tag previously published rows, recording changes without resending announcements."""
    tagged = 0
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute("SELECT event_id, title FROM events "
                            "WHERE state='published' AND topics='[]'").fetchall()
        for row in rows:
            event_id = row["event_id"]
            sources = conn.execute("SELECT caption, candidate FROM source_announcements WHERE event_id=? "
                                   "AND status='linked' ORDER BY detected_at, announcement_id", (event_id,)).fetchall()
            declared = (tag for source in sources if source["candidate"]
                        for tag in json.loads(source["candidate"]).get("topics", []))
            tags = topics.event_topics(declared, row["title"], (source["caption"] for source in sources))
            if not tags:
                continue
            update_event(conn, event_id, {"topics": tags}, "backfill event topics")
            tagged += 1
    return tagged


# ---------------------------------------------------------------- intake

def content_hash(caption: str | None, image: bytes | None, candidate: Candidate | None = None) -> str:
    h = hashlib.sha256()
    h.update(matching.norm_text(caption).encode())
    h.update(image or b"")
    if candidate is not None:
        h.update(candidate.model_dump_json().encode())
    return h.hexdigest()


def resolve_club(conn, slug: str | None) -> str | None:
    if not slug:
        return None
    want = matching.norm_text(slug)
    for row in conn.execute("SELECT club_id, display_name, aliases FROM clubs"):
        names = [row["club_id"], row["display_name"], *json.loads(row["aliases"])]
        if want in {matching.norm_text(n) for n in names}:
            return row["club_id"]
    return None


def intake(conn, source_id: str, external_id: str, caption: str | None, source_url: str | None = None,
           image: bytes | None = None, mime: str | None = None,
           observed_at: datetime | None = None, candidate: Candidate | None = None) -> dict:
    src = conn.execute("SELECT * FROM sources WHERE source_id=?", (source_id,)).fetchone()
    if not src or not src["enabled"]:
        raise NotFound(f"unknown or disabled source {source_id}")
    if candidate is not None and (src["kind"] not in ("icalendar", "public_events") or image is not None):
        raise ValueError("Structured candidates require a registered calendar/public-events source and no image")
    h = content_hash(caption, image, candidate)
    detected_at = observed_at.astimezone(timezone.utc).isoformat(timespec="seconds") if observed_at else now()
    with conn:
        inserted = conn.execute(
            "INSERT INTO source_announcements (announcement_id, source_id, external_id, source_url, "
            "content_hash, caption, detected_at, candidate) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(source_id, external_id, content_hash) DO NOTHING",
            (new_id("ann"), source_id, external_id, source_url, h, caption, detected_at,
             candidate.model_dump_json() if candidate is not None else None)).rowcount
        row = conn.execute("SELECT announcement_id, status, event_id FROM source_announcements "
                           "WHERE source_id=? AND external_id=? AND content_hash=?",
                           (source_id, external_id, h)).fetchone()
        if inserted:  # keep the raw source version even if processing later fails
            enqueue_announcement(conn, row["announcement_id"])
        conn.execute("UPDATE sources SET last_success_at=? WHERE source_id=?", (now(), source_id))
    if row["status"] != "pending":
        return _duplicate(row)
    return process(conn, row["announcement_id"], image, mime)


def _duplicate(row) -> dict:
    return {"announcement_id": row["announcement_id"], "state": row["status"],
            "event_id": row["event_id"], "duplicate": True}


def _review(conn, aid: str, reason: str, candidate_ids=None, diff=None, expected_revision=None,
            candidate: Candidate | None = None) -> dict:
    rid = new_id("rev")
    conn.execute("UPDATE source_announcements SET status='review', error=?, candidate=COALESCE(?, candidate) "
                 "WHERE announcement_id=?",
                 (reason, candidate.model_dump_json() if candidate else None, aid))
    conn.execute("INSERT INTO review_items (review_id, announcement_id, candidate_ids, expected_revision, "
                 "field_diff, created_at) VALUES (?,?,?,?,?,?)",
                 (rid, aid, json.dumps(candidate_ids or []), expected_revision, json.dumps(diff or {}), now()))
    enqueue_announcement(conn, aid)
    return {"announcement_id": aid, "state": "review", "review_id": rid, "reason": reason, "duplicate": False}


def process(conn, aid: str, image: bytes | None = None, mime: str | None = None) -> dict:
    ann = conn.execute("SELECT * FROM source_announcements WHERE announcement_id=?", (aid,)).fetchone()
    src = conn.execute("SELECT * FROM sources WHERE source_id=?", (ann["source_id"],)).fetchone()
    error = None
    try:
        if src["kind"] in ("icalendar", "public_events") and ann["candidate"]:
            cand = Candidate.model_validate_json(ann["candidate"])
        else:
            cand = extract(ann["caption"], image, mime)
        cand.topics = topics.event_topics(cand.topics, cand.title, (ann["caption"],))
        if not cand.organizer_slug:
            cand.organizer_slug = src["club_id"]
        club_id = resolve_club(conn, cand.organizer_slug)
        problems = []
        if not club_id:
            problems.append("unrecognized organizer")
        elif src["club_id"] and src["club_id"] != club_id:
            problems.append("source is not scoped to this club")
        if not cand.title:
            problems.append("missing title")
        if not cand.local_date:
            problems.append("missing date")
        else:
            cand.local_date = datetime.strptime(cand.local_date, "%Y-%m-%d").date().isoformat()
        if cand.local_start:
            cand.local_start = datetime.strptime(cand.local_start, "%H:%M").strftime("%H:%M")
        if cand.local_end:
            cand.local_end = datetime.strptime(cand.local_end, "%H:%M").strftime("%H:%M")
        if problems:
            raise ValueError("; ".join(problems))
    except ValueError as exc:
        error = f"needs review: {exc}"

    with conn:
        # The provider call runs outside the write transaction. Re-check after acquiring the
        # lock so overlapping source checks cannot publish the same pending row twice.
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute("SELECT announcement_id, status, event_id FROM source_announcements "
                               "WHERE announcement_id=?", (aid,)).fetchone()
        if current is None:
            raise NotFound(aid)
        if current["status"] != "pending":
            return _duplicate(current)
        if error:
            return _review(conn, aid, error)

        prior = conn.execute("SELECT event_id FROM source_announcements WHERE source_id=? AND external_id=? "
                             "AND event_id IS NOT NULL AND announcement_id<>? ORDER BY detected_at DESC LIMIT 1",
                             (ann["source_id"], ann["external_id"], aid)).fetchone()
        events = [get_event(conn, r["event_id"]) for r in conn.execute(
            "SELECT event_id FROM events WHERE club_id=? AND state='published'", (club_id,))]
        d = matching.decide(events, cand, prior["event_id"] if prior else None)
        if d["kind"] == "review":
            first = d["event_id"] or (d["candidate_ids"][0] if d["candidate_ids"] else None)
            ev = get_event(conn, first) if first else None
            return _review(conn, aid, d["reason"], d["candidate_ids"], d["conflicts"],
                           ev["current_revision"] if ev else None, cand)

        conn.execute("UPDATE source_announcements SET candidate=?, evidence=?, error=NULL WHERE announcement_id=?",
                     (cand.model_dump_json(), json.dumps([e.model_dump() for e in cand.evidence]), aid))
        if d["kind"] == "new":
            eid = create_event(conn, club_id, cand, aid)
            outcome = "created"
        else:
            eid = d["event_id"]
            conn.execute("UPDATE source_announcements SET event_id=?, status='linked' WHERE announcement_id=?",
                         (eid, aid))
            update_event(conn, eid, d["fills"], "corroboration from additional source")
            enqueue_announcement(conn, aid)
            outcome = "linked"
    return {"announcement_id": aid, "state": "linked", "event_id": eid, "outcome": outcome, "duplicate": False}


# ---------------------------------------------------------------- review

def resolve_review(conn, review_id: str, decision: str, expected_revision: int | None, reviewer: str) -> dict:
    r = conn.execute("SELECT * FROM review_items WHERE review_id=?", (review_id,)).fetchone()
    if not r:
        raise NotFound(review_id)
    if r["state"] != "open":
        raise ReviewConflict("review already resolved")
    ann = conn.execute("SELECT * FROM source_announcements WHERE announcement_id=?", (r["announcement_id"],)).fetchone()
    cand = Candidate.model_validate_json(ann["candidate"]) if ann["candidate"] else None
    if cand:
        cand.topics = topics.event_topics(cand.topics, cand.title, (ann["caption"],))
    ids = json.loads(r["candidate_ids"])
    result = {"review_id": review_id, "decision": decision}
    with conn:
        if decision == "reject":
            conn.execute("UPDATE source_announcements SET status='rejected' WHERE announcement_id=?", (ann["announcement_id"],))
            enqueue_announcement(conn, ann["announcement_id"])
            state = "rejected"
        elif decision in ("link", "confirm"):
            if not ids or cand is None:
                raise ValueError("review has no candidate event or extracted fields")
            ev = get_event(conn, ids[0])
            stale = r["expected_revision"] is not None and r["expected_revision"] != ev["current_revision"]
            if expected_revision != ev["current_revision"] or stale:
                raise ReviewConflict("event changed while the review was open")
            conflicts, fills = matching._diff(ev, cand)
            changes = dict(fills)
            if decision == "confirm":
                changes.update({f: v["new"] for f, v in conflicts.items()})
            result["revision"] = update_event(conn, ev["event_id"], changes, f"review {decision}", reviewer)
            conn.execute("UPDATE source_announcements SET event_id=?, status='linked' WHERE announcement_id=?",
                         (ev["event_id"], ann["announcement_id"]))
            enqueue_announcement(conn, ann["announcement_id"])
            result["event_id"] = ev["event_id"]
            state = "confirmed" if decision == "confirm" else "linked"
        else:  # separate
            club_id = resolve_club(conn, cand.organizer_slug) if cand else None
            if not club_id:
                raise ValueError("cannot create a separate event without a recognized club")
            result["event_id"] = create_event(conn, club_id, cand, ann["announcement_id"], reviewer)
            state = "separate"
        conn.execute("UPDATE review_items SET state=?, reviewer=?, resolved_at=? WHERE review_id=?",
                     (state, reviewer, now(), review_id))
    result["state"] = state
    return result


# ---------------------------------------------------------------- reading

def public_event(conn, ev: dict) -> dict:
    sources = [dict(r) for r in conn.execute(
        "SELECT DISTINCT a.source_id, a.source_url FROM source_announcements a "
        "WHERE a.event_id=? AND a.source_url IS NOT NULL", (ev["event_id"],))]
    last = conn.execute("SELECT revision, changed, created_at FROM event_revisions WHERE event_id=? AND revision>1 "
                        "AND changed<>'{}' ORDER BY revision DESC LIMIT 1", (ev["event_id"],)).fetchone()
    history = conn.execute("SELECT revision, changed, created_at FROM event_revisions WHERE event_id=? "
                           "AND revision>1 AND changed<>'{}' ORDER BY revision", (ev["event_id"],)).fetchall()
    club = conn.execute("SELECT display_name FROM clubs WHERE club_id=?", (ev["club_id"],)).fetchone()
    out = {k: ev[k] for k in ("event_id", "club_id", "current_revision", "state", *SNAP_FIELDS, "start_utc")}
    out["club_name"] = club["display_name"] if club else ev["club_id"]
    out["beginner_friendly"] = None if ev["beginner_friendly"] is None else bool(ev["beginner_friendly"])
    out["sources"] = sources
    out["place"] = places.locate(ev["venue"])  # {id, name, lat, lng} or None when not on the map
    out["history"] = [{"revision": h["revision"], "changed": json.loads(h["changed"]), "confirmed_at": h["created_at"]}
                      for h in history]
    out["unknown_fields"] = [f for f in ("local_start", "local_end", "venue", "rsvp_url") if ev[f] is None]
    out["latest_update"] = ({"revision": last["revision"], "changed": json.loads(last["changed"]),
                             "confirmed_at": last["created_at"]} if last else None)
    return out


def list_events(conn, topic: str | None = None, free: bool = False, beginner: bool = False,
                after_4pm: bool = False, include_past: bool = False) -> list[dict]:
    today = datetime.now(VAN).date().isoformat()
    out = []
    for r in conn.execute("SELECT event_id FROM events WHERE state='published' "
                          "ORDER BY local_date, local_start IS NULL, local_start"):
        ev = get_event(conn, r["event_id"])
        if not include_past and ev["local_date"] and ev["local_date"] < today:
            continue
        if topic and topic not in ev["topics"]:
            continue
        if free and ev["cost_status"] != "free":
            continue
        if beginner and ev["beginner_friendly"] != 1:
            continue
        if after_4pm and not (ev["local_start"] and ev["local_start"] >= "16:00"):
            continue
        out.append(public_event(conn, ev))
    return out


# ---------------------------------------------------------------- subscribers

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def subscribe(conn, email: str, topics: list[str], want_free: bool, want_beginner: bool, after_4pm: bool) -> dict:
    sid = new_id("sub")
    vtoken, mtoken = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    with conn:
        conn.execute(
            "INSERT INTO subscriptions (subscriber_id, email, topics, want_free, want_beginner, after_4pm, "
            "verify_token_hash, manage_token_hash) VALUES (?,?,?,?,?,?,?,?)",
            (sid, email.strip().lower(), json.dumps(topics), int(want_free), int(want_beginner), int(after_4pm),
             _hash(vtoken), _hash(mtoken)))
    return {"subscriber_id": sid, "verify_token": vtoken, "manage_token": mtoken}


def verify(conn, token: str) -> bool:
    with conn:
        cur = conn.execute("UPDATE subscriptions SET verified_at=?, verify_token_hash=NULL "
                           "WHERE verify_token_hash=? AND verified_at IS NULL", (now(), _hash(token)))
    return cur.rowcount == 1


def manage(conn, token: str, opt_out: bool) -> bool:
    with conn:
        cur = conn.execute("UPDATE subscriptions SET opted_out_at=? WHERE manage_token_hash=?",
                           (now() if opt_out else None, _hash(token)))
    return cur.rowcount == 1


# ---------------------------------------------------------------- dispatch (used by n8n)

def _sub_matches(sub, snap: dict) -> bool:
    topics = json.loads(sub["topics"])
    if topics and not set(topics) & set(snap["topics"]):
        return False
    if sub["want_free"] and snap["cost_status"] != "free":
        return False
    if sub["want_beginner"] and snap["beginner_friendly"] != 1:
        return False
    if sub["after_4pm"] and not (snap["local_start"] and snap["local_start"] >= "16:00"):
        return False
    return True


def _revision(conn, event_id: str, revision: int):
    row = conn.execute("SELECT * FROM event_revisions WHERE event_id=? AND revision=?", (event_id, revision)).fetchone()
    if not row:
        raise NotFound(f"{event_id} revision {revision}")
    return row


def dispatch_candidates(conn, event_id: str, revision: int, kind: str) -> list[str]:
    snap = json.loads(_revision(conn, event_id, revision)["snapshot"])
    subs = conn.execute("SELECT * FROM subscriptions WHERE verified_at IS NOT NULL AND opted_out_at IS NULL").fetchall()
    if kind == "new_event":
        return [s["subscriber_id"] for s in subs if _sub_matches(s, snap)]
    # corrections go to still-subscribed recipients of the original alert, whatever their filters now say
    got = {r["subscriber_id"] for r in conn.execute(
        "SELECT subscriber_id FROM deliveries WHERE event_id=? AND kind='new_event' AND state='accepted'", (event_id,))}
    return [s["subscriber_id"] for s in subs if s["subscriber_id"] in got]


def dispatch_info(conn, event_id: str, revision: int, kind: str) -> dict:
    ob = conn.execute("SELECT * FROM event_outbox WHERE event_id=? AND revision=? AND kind=?",
                      (event_id, revision, kind)).fetchone()
    if not ob:
        raise NotFound("no such outbox row")
    return {"event_id": event_id, "revision": revision, "kind": kind, "outbox_status": ob["status"],
            "candidates": dispatch_candidates(conn, event_id, revision, kind)}


def _when(date: str | None, start: str | None) -> str:
    if not date or not start:
        return "time TBD"
    d, t = datetime.strptime(date, "%Y-%m-%d"), datetime.strptime(start, "%H:%M")
    hour, suffix = t.hour % 12 or 12, "a.m." if t.hour < 12 else "p.m."
    clock = f"{hour}:{t.minute:02d} {suffix}" if t.minute else f"{hour} {suffix}"
    return f"{d.strftime('%A')} at {clock}"


def build_message(conn, event_id: str, revision: int, kind: str) -> dict:
    rev = _revision(conn, event_id, revision)
    snap, changed = json.loads(rev["snapshot"]), json.loads(rev["changed"])
    # Event pages live in the Quad frontend (frontend/); APP_BASE_URL stays the API origin.
    base = config.get("FRONTEND_BASE_URL") or config.get("APP_BASE_URL", "http://127.0.0.1:8000")
    url = f"{base.rstrip('/')}/events/{event_id}"
    when = _when(snap["local_date"], snap["local_start"])
    if kind == "new_event":
        traits = []
        if snap["cost_status"] == "free":
            traits.append("Free")
        if snap["beginner_friendly"] == 1:
            traits.append("beginner-friendly")
        line = f"{snap['title']} · {when} · {snap['venue'] or 'venue not listed'}."
        if traits:
            line += " " + " and ".join(traits) + "."
        return {"subject": f"New event: {snap['title']}", "text": f"{line} View event: {url}"}
    parts = []
    if "venue" in changed:
        parts.append(f"Room change for {snap['title']}. {changed['venue']['old']} → {changed['venue']['new']}.")
    if "local_date" in changed or "local_start" in changed:
        parts.append(f"Schedule change for {snap['title']}. It now starts {when}.")
    elif "venue" in changed:
        parts.append(f"The event still starts {when}.")
    return {"subject": f"Update: {snap['title']}", "text": " ".join(parts) + f" View updated event: {url}"}


def claim(conn, subscriber_id: str, event_id: str, revision: int, kind: str) -> dict:
    """Atomically claim one delivery. Safe to call twice: a finished or leased delivery is not re-issued."""
    with conn:
        sub = conn.execute("SELECT * FROM subscriptions WHERE subscriber_id=?", (subscriber_id,)).fetchone()
        ev = get_event(conn, event_id)
        if not sub or not ev:
            raise NotFound("subscriber or event")
        if sub["opted_out_at"] or not sub["verified_at"]:
            return {"status": "skipped", "reason": "unsubscribed"}
        if ev["state"] != "published":
            return {"status": "skipped", "reason": "event not published"}
        if subscriber_id not in dispatch_candidates(conn, event_id, revision, kind):
            return {"status": "skipped", "reason": "not eligible"}
        existing = conn.execute("SELECT * FROM deliveries WHERE subscriber_id=? AND event_id=? AND revision=? AND kind=?",
                                (subscriber_id, event_id, revision, kind)).fetchone()
        token = secrets.token_urlsafe(16)
        expires = (datetime.now(timezone.utc) + timedelta(seconds=LEASE_SECONDS)).isoformat(timespec="seconds")
        if existing:
            if existing["state"] in ("accepted", "skipped", "failed"):
                return {"status": "skipped", "reason": f"already {existing['state']}"}
            if existing["state"] == "claimed" and existing["claim_expires"] > now():
                return {"status": "leased"}
            did = existing["delivery_id"]
            conn.execute("UPDATE deliveries SET state='claimed', claim_token=?, claim_expires=? WHERE delivery_id=?",
                         (token, expires, did))
            payload = json.loads(existing["payload"])
        else:
            did = new_id("dlv")
            payload = {"to": sub["email"], **build_message(conn, event_id, revision, kind)}
            conn.execute("INSERT INTO deliveries (delivery_id, subscriber_id, event_id, revision, kind, payload, "
                         "state, claim_token, claim_expires) VALUES (?,?,?,?,?,?,'claimed',?,?)",
                         (did, subscriber_id, event_id, revision, kind, json.dumps(payload), token, expires))
    return {"status": "claimed", "delivery_id": did, "claim_token": token,
            "idempotency_key": f"club-alert/{did}", **payload}


def record_result(conn, delivery_id: str, claim_token: str, outcome: str, provider_msg_id: str | None) -> dict:
    with conn:
        d = conn.execute("SELECT * FROM deliveries WHERE delivery_id=?", (delivery_id,)).fetchone()
        if not d:
            raise NotFound(delivery_id)
        if d["state"] != "claimed" or d["claim_token"] != claim_token:
            raise ReviewConflict("claim token is not current")
        state = {"accepted": "accepted", "terminal": "failed", "retryable": "pending"}[outcome]
        conn.execute("UPDATE deliveries SET state=?, provider_msg_id=?, claim_token=NULL, claim_expires=NULL "
                     "WHERE delivery_id=?", (state, provider_msg_id, delivery_id))
        # complete the outbox row once every eligible recipient is settled
        settled = {r["subscriber_id"] for r in conn.execute(
            "SELECT subscriber_id FROM deliveries WHERE event_id=? AND revision=? AND kind=? "
            "AND state IN ('accepted','skipped','failed')", (d["event_id"], d["revision"], d["kind"]))}
        todo = set(dispatch_candidates(conn, d["event_id"], d["revision"], d["kind"])) - settled
        if not todo:
            conn.execute("UPDATE event_outbox SET status='complete' WHERE event_id=? AND revision=? AND kind=?",
                         (d["event_id"], d["revision"], d["kind"]))
    return {"delivery_id": delivery_id, "state": state}
