"""Discover every AMS directory entry and its explicitly linked club channels."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import socket
from threading import Lock
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

DIRECTORY_URL = "https://amsclubs.ca/all-clubs/"
USER_AGENT = "ClubAlerts/0.1 (+https://github.com/freddyp3/hackcamp2026)"
MAX_BYTES = 2 * 1024 * 1024
ROOT = Path(__file__).resolve().parent.parent
KNOWN_CLUBS = {
    "anime-club": "ubc-anime", "chess-club": "ubc-chess", "wargamers": "ubc-wargamers",
    "asian-brush-calligraphy": "ubc-calligraphy", "speech-and-linguistics-student-association": "ubc-salsa",
    "computer-science-student-society": "ubc-csss", "nwplus": "ubc-nwplus",
    "women-in-computer-science": "ubc-wics", "women-in-data-science": "ubc-wids",
    "ubc-biztech": "ubc-biztech", "launch-pad": "ubc-launchpad",
}
KNOWN_INSTAGRAM = {"ubc_csss": "ubc-csss", "ubcwics": "ubc-wics", "nwplusubc": "ubc-nwplus",
                   "widsubc": "ubc-wids", "ubcani": "ubc-anime", "ubcchessclub": "ubc-chess",
                   "ubcabcalligraphy": "ubc-calligraphy", "ubcbiztech": "ubc-biztech", "ubclaunchpad": "ubc-launchpad"}
SOCIAL_HOSTS = {"instagram.com", "facebook.com", "fb.com", "linkedin.com", "youtube.com", "youtu.be",
                "twitter.com", "x.com", "discord.com", "discord.gg", "tiktok.com", "linktr.ee",
                "beacons.ai", "linkin.bio", "ams.ubc.ca", "amsclubs.ca"}


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def public_url(value, base="", *, resolve=False):
    """Reject private destinations, including each redirect, before making a request."""
    parsed = urlsplit(urljoin(base, value.strip()))
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if (parsed.scheme not in ("http", "https") or not host or parsed.username or parsed.password
            or parsed.port not in (None, 80, 443) or "." not in host
            or host.endswith((".local", ".localhost", ".private", ".internal", ".test"))):
        raise ValueError("Public website URL required")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Private website destination refused")
    if resolve:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError("Private website destination refused")
    # Prefer HTTPS even for outdated HTTP links in the club directory.
    return urlunsplit(("https", parsed.hostname.lower(), parsed.path or "/", parsed.query, ""))


def instagram_url(value):
    parsed = urlsplit(urljoin("https://www.instagram.com/", value))
    if (parsed.hostname or "").lower().removeprefix("www.") != "instagram.com":
        return None
    parts = parsed.path.strip("/").split("/")
    if len(parts) == 2 and parts[0] == "_u":
        parts = parts[1:]
    if len(parts) != 1 or not re.fullmatch(r"[A-Za-z0-9_.]{1,30}", parts[0]):
        return None
    if parts[0].lower() in {"p", "reel", "reels", "stories", "explore", "accounts", "direct", "about"}:
        return None
    return f"https://www.instagram.com/{parts[0].lower()}/"


class Fetcher:
    """Bounded, cached, public-only downloads with a per-host request interval."""
    def __init__(self, cache_dir=None, interval=0.5):
        self.cache = Path(cache_dir) if cache_dir else None
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)
        self.interval, self.lock, self.next_at = interval, Lock(), {}
        self.client = httpx.Client(timeout=httpx.Timeout(15, connect=8), headers={"User-Agent": USER_AGENT})

    def close(self):
        self.client.close()

    def get(self, url):
        url = public_url(url)
        cache_key = hashlib.sha256(url.encode()).hexdigest()
        path = self.cache / f"{cache_key}.json" if self.cache else None
        if path and path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        original = url
        for _ in range(5):
            url = public_url(url, resolve=True)
            host = urlsplit(url).hostname
            with self.lock:
                wait = max(0, self.next_at.get(host, 0) - time.monotonic())
                self.next_at[host] = time.monotonic() + wait + self.interval
            if wait:
                time.sleep(wait)
            with self.client.stream("GET", url, follow_redirects=False) as response:
                if response.is_redirect:
                    url = public_url(response.headers["location"], url)
                    continue
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise ValueError("Website exceeds download limit")
                result = {"url": str(response.url), "status": response.status_code,
                          "text": bytes(body).decode("utf-8", errors="replace"), "checked_at": stamp()}
                if path:
                    path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
                return result
        raise ValueError("Too many website redirects")


def directory_page(text):
    soup = BeautifulSoup(text, "html.parser")
    clubs = []
    for link in soup.select("a.club-item-link[href]"):
        heading = link.select_one("h2")
        url = public_url(link["href"])
        if urlsplit(url).hostname != "amsclubs.ca" or not heading:
            raise ValueError("Unexpected AMS directory entry")
        slug = urlsplit(url).path.strip("/")
        clubs.append({"club_id": KNOWN_CLUBS.get(slug, "ams-" + slug),
                      "name": heading.get_text(" ", strip=True), "directory_url": url})
    if not clubs:
        raise ValueError("AMS directory format changed")
    pages = [int(m[1]) for a in soup.select('a[href]')
             if (m := re.search(r"/all-clubs/+pagenum/(\d+)/", a["href"]))]
    count = re.search(r"\(\s*(\d+)\s*\)\s*clubs found", soup.get_text(" ", strip=True), re.I)
    return clubs, max(pages, default=1), int(count[1]) if count else None


def channels(text, base):
    soup = BeautifulSoup(text, "html.parser")
    instagram, websites, hubs = set(), set(), set()
    # Official AMS social links are separate from members' bios and unrelated footer links.
    links = soup.select(".club-sm a[href]") if urlsplit(base).hostname == "amsclubs.ca" else soup.select("a[href]")
    for link in links:
        try:
            url = public_url(link["href"], base)
        except ValueError:
            continue
        ig = instagram_url(url)
        host = urlsplit(url).hostname.removeprefix("www.")
        if ig:
            instagram.add(ig)
        elif host in {"linktr.ee", "beacons.ai", "linkin.bio"}:
            hubs.add(url)
        elif host not in SOCIAL_HOSTS and not any(host.endswith("." + s) for s in SOCIAL_HOSTS):
            if urlsplit(base).hostname == "amsclubs.ca":
                websites.add(url)
    return {"instagram_urls": sorted(instagram), "website_urls": sorted(websites), "link_hubs": sorted(hubs)}


def event_links(text, base):
    soup = BeautifulSoup(text, "html.parser")
    found = []
    host = urlsplit(base).hostname.removeprefix("www.")
    for a in soup.select("a[href]"):
        try:
            url = public_url(a["href"], base)
        except ValueError:
            continue
        if urlsplit(url).hostname.removeprefix("www.") != host:
            continue
        if re.search(r"(?:^|/)(?:events?|calendar|workshops?)(?:/|$)", urlsplit(url).path, re.I):
            if url not in found:
                found.append(url)
    return sorted(found, key=lambda u: (len(urlsplit(u).path), u))[:2]


def inspect_club(club, fetcher):
    club = dict(club)
    try:
        page = fetcher.get(club["directory_url"])
        club.update(directory_status=page["status"], checked_at=page["checked_at"])
        if page["status"] != 200:
            return {**club, "error": f"HTTP {page['status']}", "website_urls": [], "instagram_urls": []}
        club.update(channels(page["text"], page["url"]))
        identifiers = {KNOWN_INSTAGRAM[u.rstrip("/").rsplit("/", 1)[-1]] for u in club["instagram_urls"]
                       if u.rstrip("/").rsplit("/", 1)[-1] in KNOWN_INSTAGRAM}
        if len(identifiers) == 1:
            club["club_id"] = identifiers.pop()
        # Follow only link hubs explicitly advertised by this club, not social search results.
        for hub in club["link_hubs"][:2]:
            try:
                linked = fetcher.get(hub)
                if linked["status"] == 200:
                    club["instagram_urls"] = sorted(set(club["instagram_urls"]) |
                                                    set(channels(linked["text"], linked["url"])["instagram_urls"]))
            except (httpx.HTTPError, OSError, ValueError):
                pass
        club["websites"] = []
        for url in club["website_urls"][:3]:
            site = {"url": url}
            try:
                result = fetcher.get(url)
                site.update(final_url=result["url"], status=result["status"], checked_at=result["checked_at"])
                if result["status"] == 200:
                    site["event_urls"] = event_links(result["text"], result["url"])
                    club["instagram_urls"] = sorted(set(club["instagram_urls"]) |
                                                    set(channels(result["text"], result["url"])["instagram_urls"]))
                    for target in site["event_urls"]:
                        detail = fetcher.get(target)
                        site.setdefault("event_checks", []).append({"url": target, "status": detail["status"],
                                                                     "checked_at": detail["checked_at"]})
            except (httpx.HTTPError, OSError, ValueError) as exc:
                site["error"] = type(exc).__name__
            club["websites"].append(site)
        return club
    except (httpx.HTTPError, OSError, ValueError) as exc:
        return {**club, "error": type(exc).__name__, "website_urls": [], "instagram_urls": []}


def discover(fetcher, workers=4):
    first = fetcher.get(DIRECTORY_URL)
    if first["status"] != 200:
        raise ValueError(f"AMS directory returned HTTP {first['status']}")
    clubs, pages, expected = directory_page(first["text"])
    if pages > 60:
        raise ValueError("AMS directory exceeds page limit")
    for page_no in range(2, pages + 1):
        result = fetcher.get(f"{DIRECTORY_URL}pagenum/{page_no}/")
        if result["status"] != 200:
            raise ValueError(f"Directory page {page_no}: HTTP {result['status']}")
        clubs.extend(directory_page(result["text"])[0])
    unique = {c["directory_url"]: c for c in clubs}
    if expected is not None and len(unique) != expected:
        raise ValueError(f"Incomplete directory: {len(unique)} of {expected} clubs")
    print(json.dumps({"directory_pages": pages, "clubs_found": len(unique)}), flush=True)
    inspected = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for club in pool.map(lambda c: inspect_club(c, fetcher), unique.values()):
            inspected.append(club)
            if len(inspected) % 25 == 0:
                print(json.dumps({"clubs_inspected": len(inspected)}), flush=True)
    return {"directory_url": DIRECTORY_URL, "discovered_at": stamp(), "expected_clubs": expected,
            "clubs": inspected}


def watchlist(inventory, previous):
    accounts = {a["url"]: {k: v for k, v in a.items() if k != "clubs"} for a in previous.get("accounts", [])}
    for club in inventory["clubs"]:
        for url in club["instagram_urls"]:
            account = accounts.setdefault(url, {"club": club["name"], "url": url,
                                                "official_page": club["directory_url"]})
            account.setdefault("clubs", [])
            if not any(c["club_id"] == club["club_id"] for c in account["clubs"]):
                account["clubs"].append({"club_id": club["club_id"], "name": club["name"]})
    return {"mode": "pending_activation", "note": "Official links from AMS club pages and their linked websites. "
            "Scheduled checks require the persistent browser and cost approval; missing Instagram links are not guessed.",
            "accounts": sorted(accounts.values(), key=lambda a: a["url"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    fetcher = Fetcher(ROOT / "data/source-discovery/cache")
    try:
        inventory = discover(fetcher, max(1, min(args.workers, 6)))
    finally:
        fetcher.close()
    destination = ROOT / "config/club-directory.json"
    destination.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    path = ROOT / "config/instagram-watchlist.json"
    path.write_text(json.dumps(watchlist(inventory, json.loads(path.read_text(encoding="utf-8"))),
                               indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    clubs = inventory["clubs"]
    print(json.dumps({"clubs": len(clubs), "club_page_errors": sum(bool(c.get("error")) for c in clubs),
                      "with_websites": sum(bool(c["website_urls"]) for c in clubs),
                      "with_instagram": sum(bool(c["instagram_urls"]) for c in clubs)}))


if __name__ == "__main__":
    main()
