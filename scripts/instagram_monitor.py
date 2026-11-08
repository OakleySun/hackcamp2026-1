"""Bounded, twice-daily caption checks using the existing Maritime Linux computer."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import time

import httpx

from scripts.club_directory import instagram_url, stamp
from scripts.club_sites import read_json, save_json
from scripts.public_sources import _listing

API = "https://api.maritime.sh"
STOP_STATUSES = {"login_required", "rate_limited", "browser_error"}


def window(now):
    """Two UTC slots; the existing 15-minute trigger claims each at most once."""
    return now.strftime("%Y-%m-%d") + ("-am" if now.hour < 12 else "-pm")


def post_listing(post, account):
    url = post["url"]
    text = post.get("caption", "").strip()
    alt = "\n".join(post.get("image_alt", []))
    # Every Instagram announcement stays in review. Posting dates and alt text are not event dates.
    organizer = account.get("clubs", [{}])[0].get("club_id") if len(account.get("clubs", [])) == 1 else None
    title = text.splitlines()[0][:180] if text else account["club"] + ": Instagram announcement"
    return _listing(url, url, title, organizer=organizer,
                    description=f"Club: {account['club']}\nCaption: {text}\nImage alt text: {alt}"[:18000])


def check(client, app_url, source_id, token, private_backend_host, options):
    from scripts.check_sources import Feed, submit_feed

    blank = {"checked": 0, "submitted": 0, "unchanged": 0, "review": 0, "failed": 0}
    if os.environ.get("MARITIME_INSTAGRAM_ENABLED", "false").lower() != "true":
        return {**blank, "browser_status": "disabled"}
    key = os.environ.get("MARITIME_COMPUTERS_KEY", "")
    if not key:
        raise ValueError("Missing scoped Computers API credential")
    cid = options.get("computer_id")
    if not cid:
        raise ValueError("Existing Instagram computer ID is required")
    accounts = read_json(options.get("watchlist", "config/instagram-watchlist.json"), {}).get("accounts", [])
    if not accounts:
        raise ValueError("Instagram watchlist is empty")
    state_path = os.environ.get("MARITIME_INSTAGRAM_STATE", "data/instagram-monitor-state.json")
    state = read_json(state_path, {"accounts": {}, "windows": {}})
    state.setdefault("accounts", {})
    state.setdefault("windows", {})
    now = datetime.now(timezone.utc)
    slot = window(now)
    if state.get("cooldown_until", "") > now.isoformat(timespec="seconds"):
        return {**blank, "browser_status": state.get("last_status", "cooldown"), "cooldown_until": state["cooldown_until"]}
    if slot in state["windows"]:
        return {**blank, "browser_status": "already_checked_this_window"}
    with httpx.Client(base_url=API, timeout=40, headers={"Authorization": "Bearer " + key}) as api:
        def call(method, path, **kwargs):
            response = api.request(method, f"/api/v1/computers/{cid}" + path, **kwargs)
            if not response.is_success:
                raise ValueError(f"Computers API HTTP {response.status_code}")
            return response.json()

        desktop = call("GET", "")
        if desktop.get("mode") == "human":
            return {**blank, "browser_status": "human_in_control"}
        # Persist the claim before waking; an interrupted worker must not start the slot again.
        state["windows"] = {k: v for k, v in state["windows"].items() if k[:10] >= (now - timedelta(days=3)).strftime("%Y-%m-%d")}
        state["windows"][slot] = {"started_at": stamp(), "status": "running"}
        save_json(state_path, state)
        started, result, attempted = time.monotonic(), dict(blank), 0
        budget = max(60, min(int(options.get("max_seconds_per_window", 3300)), 3300))
        due = sorted(accounts, key=lambda a: state["accounts"].get(a["url"], {}).get("checked_at", ""))
        try:
            call("POST", "/wake")
            for account in due:
                if time.monotonic() - started >= budget:
                    result["browser_status"] = "window_budget_reached"
                    break
                url = instagram_url(account["url"])
                if not url:
                    continue
                previous = state["accounts"].get(url, {})
                seen = previous.get("seen_posts", [])[-60:]
                command = ("/home/desk/club-alerts/.venv/bin/python /home/desk/club-alerts/instagram_reader.py "
                           + shlex.quote(url) + " --seen " + shlex.quote(json.dumps(seen)))
                execution = call("POST", "/exec", json={"command": command, "timeoutS": 28})
                try:
                    data = json.loads(execution.get("stdout", "").strip().splitlines()[-1])
                except (IndexError, ValueError):
                    data = {"status": "browser_error", "posts": []}
                attempted += 1
                posts = data.get("posts", [])
                listings = [post_listing(p, account) for p in posts
                            if p.get("url", "").startswith(("https://www.instagram.com/p/", "https://www.instagram.com/reel/"))]
                counts = submit_feed(client, Feed.model_validate({"events": listings}), app_url,
                                     source_id, token, private_backend_host)
                for field in blank:
                    result[field] += counts[field]
                if counts["failed"]:
                    result["browser_status"] = "intake_failed"
                    break
                status = data.get("status", "browser_error")
                state["accounts"][url] = {"checked_at": stamp(), "status": status,
                                           "seen_posts": list(dict.fromkeys([*seen, *[p["url"] for p in posts]]))[-60:]}
                state["last_status"] = status
                if status in STOP_STATUSES:
                    state["cooldown_until"] = (now + timedelta(hours=24)).isoformat(timespec="seconds")
                    result["browser_status"] = status
                    result["failed"] += 1
                    save_json(state_path, state)
                    break
                save_json(state_path, state)
                # One profile at a time; no proxy rotation or challenge bypass.
                time.sleep(3)
            else:
                result["browser_status"] = "watchlist_checked"
        finally:
            elapsed = round(time.monotonic() - started, 1)
            state["windows"][slot].update(completed_at=stamp(), elapsed_seconds=elapsed,
                                          accounts_checked=attempted, status=result.get("browser_status", "interrupted"))
            save_json(state_path, state)
            try:
                desktop = call("GET", "")
                if desktop.get("mode") != "human":
                    call("POST", "/sleep")
            except (ValueError, httpx.HTTPError):
                result["sleep_confirmation"] = "unavailable"
                result["failed"] += 1
        result.update(accounts_checked=attempted, watchlist_accounts=len(accounts), awake_seconds=elapsed)
        return result
