"""Look up pending UBC Events announcements on the official calendar."""

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from html import unescape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx

CALENDAR = "https://events.ubc.ca/wp-json/tribe/events/v1/events"
VANCOUVER = ZoneInfo("America/Vancouver")
STATUS = Path("/data/quad-enrichment-status.json")
RUN = Lock()


def title_key(value):
    return re.sub(r"[^a-z0-9 ]", "", unescape(value or "").lower()).strip()


def official_key(url):
    parts = urlsplit(url)
    if parts.scheme == "https" and parts.netloc == "events.ubc.ca" and not parts.query:
        return "https://events.ubc.ca" + parts.path.rstrip("/")
    return None


def calendar_matches(client, items, today):
    wanted = {(item["url"], title_key(item["title"])) for item in items}
    matches = defaultdict(dict)
    for page in range(1, 7):
        response = client.get(CALENDAR, params={"start_date": f"{today} 00:00:00",
                              "end_date": f"{today + timedelta(days=60)} 23:59:59",
                              "per_page": 50, "page": page})
        response.raise_for_status()
        payload = response.json()
        for event in payload["events"]:
            key = (official_key(event["url"]), title_key(event.get("title")))
            status = str(event.get("event_status") or "").lower()
            if (key in wanted and event.get("status") == "publish" and event.get("timezone") == "America/Vancouver"
                    and event.get("start_date") and not any(word in status for word in ("cancel", "postpon"))):
                matches[key][(event["id"], event["start_date"])] = event
        if page >= int(payload["total_pages"]):
            return matches
    raise ValueError("The official calendar exceeds the lookup page budget")


def finding(event):
    start = datetime.fromisoformat(event["start_date"])
    end = datetime.fromisoformat(event["end_date"]) if event.get("end_date") else None
    all_day = event.get("all_day", False)
    organizers = event.get("organizer") or []
    organizer = next((unescape(o["organizer"]) for o in organizers if isinstance(o, dict) and o.get("organizer")), None)
    venue = event.get("venue") or {}
    name = unescape(venue.get("venue") or "") if isinstance(venue, dict) else ""
    return {
        "url": event["url"], "title": unescape(event["title"]), "organizer": organizer,
        "local_date": start.date().isoformat(), "local_start": None if all_day else start.strftime("%H:%M"),
        "local_end": end.strftime("%H:%M") if end and not all_day and end.date() == start.date() else None,
        "venue": name if name and name.casefold() != "see description" else None,
        "cost_status": "free" if str(event.get("cost", "")).strip().casefold() in ("free", "0", "$0") else "unknown",
    }


def enrich():
    origin = os.environ["QUAD_API_URL"].rstrip("/")
    token = os.environ["REVIEW_ENRICHMENT_TOKEN"]
    with (httpx.Client(base_url=origin, headers={"Authorization": f"Bearer {token}"}, timeout=12) as api,
          httpx.Client(headers={"User-Agent": "Quad event review (+https://github.com/freddyp3/hackcamp2026)"},
                       timeout=10) as public):
        items = api.get("/api/enrichment/work").raise_for_status().json()
        if not items:
            return {"checked": 0, "suggestions": 0}
        matches = calendar_matches(public, items, datetime.now(VANCOUVER).date())
        results = []
        for item in items:
            options = matches[(item["url"], title_key(item["title"]))]
            evidence = finding(next(iter(options.values()))) if len(options) == 1 else None
            results.append({"review_id": item["review_id"], "finding": evidence})
        response = api.post("/api/enrichment/results", json={"results": results}).raise_for_status().json()
    return {"checked": len(items), **response}


def run():
    try:
        try:
            result = {"state": "complete", **enrich()}
        except httpx.HTTPStatusError as exc:
            result = {"state": "failed", "error": f"HTTP {exc.response.status_code}"}
        except (httpx.RequestError, ValueError, KeyError, TypeError) as exc:
            result = {"state": "failed", "error": type(exc).__name__}
        result["completed_at"] = datetime.now(VANCOUVER).isoformat(timespec="seconds")
        temp = STATUS.with_suffix(".tmp")
        temp.write_text(json.dumps(result), encoding="utf-8")
        temp.replace(STATUS)
        print(json.dumps(result), flush=True)
    finally:
        RUN.release()


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self.reply(200, {"status": "ok"})
        if self.path == "/status":
            previous = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else {"state": "idle"}
            return self.reply(200, {**previous, "running": RUN.locked()})
        return self.reply(404, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/chat":
            return self.reply(404, {"error": "not_found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 4096:
                raise ValueError
            message = json.loads(self.rfile.read(length))["message"].strip().lower()
        except (ValueError, KeyError, AttributeError, TypeError):
            return self.reply(400, {"error": "invalid_message"})
        if message == "status":
            previous = STATUS.read_text(encoding="utf-8") if STATUS.exists() else '{"state":"idle"}'
            return self.reply(200, {"response": previous, "running": RUN.locked()})
        if message != "check":
            return self.reply(200, {"response": "Send check to start or status to see the last result."})
        if not RUN.acquire(blocking=False):
            return self.reply(200, {"response": "A review check is already running."})
        Thread(target=run, daemon=True).start()
        return self.reply(200, {"response": "Review enrichment started."})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "18789"))), Handler).serve_forever()
