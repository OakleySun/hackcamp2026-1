"""Rotate through all directory clubs, inspecting their published event pages daily."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import time

import httpx
from bs4 import BeautifulSoup

from scripts.calendar_feed import VANCOUVER
from scripts.club_directory import Fetcher, public_url, stamp
from scripts.public_sources import _listing


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def site_listings(text, url, club, now=None):
    """Only structured Event dates are publishable; other event text goes to review."""
    now = now or datetime.now(timezone.utc)
    soup = BeautifulSoup(text, "html.parser")
    records = []

    def walk(value):
        if isinstance(value, list):
            for item in value:
                yield from walk(item)
        elif isinstance(value, dict):
            kind = value.get("@type", [])
            if isinstance(kind, str):
                kind = [kind]
            if any(k == "Event" or str(k).endswith("Event") for k in kind):
                yield value
            for key in ("@graph", "itemListElement", "item", "mainEntity"):
                if key in value:
                    yield from walk(value[key])

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            nodes = list(walk(json.loads(script.get_text())))
        except (ValueError, TypeError):
            continue
        for node in nodes:
            try:
                date_text = node["startDate"]
                start = datetime.fromisoformat(date_text.replace("Z", "+00:00"))
                start = start.replace(tzinfo=VANCOUVER) if start.tzinfo is None else start.astimezone(VANCOUVER)
                if not now.astimezone(VANCOUVER).date() <= start.date() <= (now + timedelta(days=60)).date():
                    continue
                if "Cancelled" in str(node.get("eventStatus", "")):
                    continue
                target = public_url(node.get("url") or url, url)
                title = str(node["name"]).strip()
                location = node.get("location")
                venue = location.get("name") if isinstance(location, dict) else location if isinstance(location, str) else None
                identity = str(node.get("@id") or target)
                if target.rstrip("/") == url.rstrip("/"):
                    identity += f"|{title}|{start.date()}"
                item = _listing(club["club_id"] + "|" + identity, target, title, start=start, venue=venue,
                                organizer=club["club_id"], all_day="T" not in date_text,
                                description=BeautifulSoup(str(node.get("description", "")), "html.parser").get_text(" ", strip=True))
                records.append(item)
            except (KeyError, ValueError, AttributeError, TypeError):
                continue
    if records:
        return records
    for node in soup.select("script, style, nav, header, footer, noscript"):
        node.decompose()
    content = (soup.select_one("main") or soup).get_text(" ", strip=True)
    dated = re.search(r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|"
                      r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2}\b|"
                      r"\b20\d{2}-\d{2}-\d{2}\b", content, re.I)
    if dated and re.search(r"\b(?:event|workshop|conference|hackathon|social|meeting|competition)s?\b", content, re.I):
        # A whole listings page is an announcement to review, never a guessed event.
        records.append(_listing(club["club_id"] + "|" + url, url, club["name"] + ": event announcements",
                                organizer=club["club_id"], description=content[:9000]))
    return records


def check(client, app_url, source_id, token, private_backend_host, options):
    from scripts.check_sources import Feed, submit_feed

    inventory = read_json(options.get("inventory", "config/club-directory.json"), {})
    if not inventory.get("clubs"):
        raise ValueError("Club directory inventory is missing")
    state_path = os.environ.get("MARITIME_SITE_STATE", options.get("state", "data/club-sites-state.json"))
    state = read_json(state_path, {"clubs": {}})
    state.setdefault("clubs", {})
    now = datetime.now(timezone.utc)
    due = [c for c in inventory["clubs"] if state["clubs"].get(c["club_id"], {}).get("checked_at", "") <
           (now - timedelta(hours=24)).isoformat(timespec="seconds")]
    due.sort(key=lambda c: state["clubs"].get(c["club_id"], {}).get("checked_at", ""))
    selected = due[:max(1, min(int(options.get("batch_size", 10)), 15))]
    events, failures, completed, site_checks = [], 0, [], 0
    fetcher, started = Fetcher(interval=0.7), time.monotonic()
    try:
        for club in selected:
            if time.monotonic() - started > 360:
                break
            report = {"checked_at": stamp(), "pages": []}
            for website in club.get("websites", []):
                home = website.get("final_url") or website["url"]
                targets = [home, *website.get("event_urls", [])][:3]
                for target in dict.fromkeys(targets):
                    if len(events) >= 50 or time.monotonic() - started > 360:
                        break
                    try:
                        page = fetcher.get(target)
                        site_checks += 1
                        report["pages"].append({"url": target, "status": page["status"]})
                        if page["status"] == 200:
                            found = site_listings(page["text"], page["url"], club, now)
                            if len(events) + len(found) > 50:
                                raise ValueError("More than 50 announcements in a website batch; reduce batch size")
                            events.extend(found)
                        else:
                            failures += 1
                    except (httpx.HTTPError, OSError, ValueError) as exc:
                        failures += 1
                        report["pages"].append({"url": target, "error": type(exc).__name__})
            if not club.get("websites"):
                report["status"] = "no_external_website_listed"
            else:
                report["status"] = "checked" if report["pages"] else "deferred"
            completed.append((club["club_id"], report))
    finally:
        fetcher.close()
    unique = {item["external_id"]: item for item in events}
    result = submit_feed(client, Feed.model_validate({"events": list(unique.values())}), app_url,
                         source_id, token, private_backend_host)
    # Advance only after intake accepted the batch; a failed submission is safely replayed.
    if result["failed"] == 0:
        state["clubs"].update(completed)
        state["updated_at"] = stamp()
        save_json(state_path, state)
    result["failed"] += failures
    result.update(clubs_checked=len(completed), website_pages_checked=site_checks,
                  clubs_remaining=max(0, len(due) - len(completed)))
    return result
