"""Check approved public sources and submit their announcements to Club Alerts."""

import json
import argparse
import os
from datetime import datetime, timezone
from pathlib import Path
from sys import stderr

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field, HttpUrl

from scripts.calendar_feed import calendar_feed
from scripts.public_sources import public_feed

MAX_FEED_BYTES = 256 * 1024
MAX_CALENDAR_BYTES = 2 * 1024 * 1024
MAX_FLYER_BYTES = 5 * 1024 * 1024
COUNT_FIELDS = ("checked", "submitted", "unchanged", "review", "failed")


class Listing(BaseModel):
    external_id: str = Field(min_length=1, max_length=200)
    source_url: HttpUrl
    caption: str = Field(default="", max_length=20_000)
    flyer_url: HttpUrl | None = None
    candidate: dict | None = None


class Feed(BaseModel):
    events: list[Listing] = Field(max_length=50)


def _service_url(value: str, private_backend_host: str = "") -> httpx.URL:
    try:
        url = httpx.URL(value)
    except httpx.InvalidURL as exc:
        raise ValueError("Invalid service URL") from exc
    loopback = url.host in ("localhost", "127.0.0.1", "::1")
    private_backend = bool(private_backend_host) and url.host == private_backend_host and url.host.endswith(".private")
    if not url.host or url.userinfo or not (url.scheme == "https" or ((loopback or private_backend) and url.scheme == "http")):
        raise ValueError("Use an HTTPS URL, or HTTP on loopback for local testing")
    return url


def _download(client: httpx.Client, url: httpx.URL, limit: int) -> bytes:
    data = bytearray()
    with client.stream("GET", url, follow_redirects=False) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            if len(data) + len(chunk) > limit:
                raise ValueError("Feed or flyer exceeds the size limit")
            data.extend(chunk)
    return bytes(data)


def check_source(client: httpx.Client, feed_url: str, app_url: str, source_id: str, token: str,
                 feed_format: str = "json", lookahead_days: int = 60, private_backend_host: str = "",
                 options: dict | None = None) -> dict:
    if not source_id or not token:
        raise ValueError("Set MARITIME_SOURCE_ID and SOURCE_INGEST_TOKEN")
    feed_endpoint = _service_url(feed_url)
    if feed_format == "ical":
        feed = Feed.model_validate(calendar_feed(
            _download(client, feed_endpoint, MAX_CALENDAR_BYTES), days=lookahead_days))
    elif feed_format == "json":
        feed = Feed.model_validate_json(_download(client, feed_endpoint, MAX_FEED_BYTES))
    else:
        feed = Feed.model_validate(public_feed(client, str(feed_endpoint), feed_format,
                                              days=lookahead_days, options=options))
    return submit_feed(client, feed, app_url, source_id, token, private_backend_host, feed_endpoint)


def submit_feed(client, feed, app_url, source_id, token, private_backend_host="", feed_endpoint=None):
    """Share deterministic intake and deduplication with website and browser batches."""
    intake = _service_url(app_url, private_backend_host).join("/api/intake")
    headers = {"Authorization": f"Bearer {token}"}
    observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    summary = {"checked": len(feed.events), "submitted": 0, "unchanged": 0, "review": 0, "failed": 0}
    for event in feed.events:
        payload = {
            "source_id": source_id,
            "external_id": event.external_id,
            "source_url": str(event.source_url),
            "caption": event.caption,
            "observed_at": observed_at,
        }
        if event.candidate is not None:
            if event.flyer_url:
                raise ValueError("Structured calendar listings cannot include a flyer")
            payload["candidate"] = event.candidate
        try:
            if event.flyer_url:
                flyer_url = _service_url(str(event.flyer_url))
                if feed_endpoint is None or (flyer_url.scheme, flyer_url.netloc) != (feed_endpoint.scheme, feed_endpoint.netloc):
                    raise ValueError("Flyers must be hosted on the approved feed origin")
                image = _download(client, flyer_url, MAX_FLYER_BYTES)
                response = client.post(
                    intake.join("/api/intake/upload"), data=payload, files={"flyer": ("flyer", image)},
                    headers=headers, follow_redirects=False,
                )
            else:
                if not event.caption.strip():
                    raise ValueError("A listing needs a caption or flyer")
                response = client.post(intake, json=payload, headers=headers, follow_redirects=False)
            response.raise_for_status()
            result = response.json()
            if result["duplicate"]:
                summary["unchanged"] += 1
            else:
                summary["submitted"] += 1
                if result["state"] == "review":
                    summary["review"] += 1
        except httpx.HTTPStatusError as exc:
            summary["failed"] += 1
            print(f"Listing {summary['failed']} failure: HTTP {exc.response.status_code}", file=stderr)
        except (httpx.RequestError, ValueError, KeyError, TypeError) as exc:
            summary["failed"] += 1
            print(f"Listing {summary['failed']} failure: {type(exc).__name__}", file=stderr)
    return summary


def check_sources(client: httpx.Client, sources: list[dict], app_url: str, token: str,
                  private_backend_host: str = "") -> dict:
    """Continue checking other sources when a public site is unavailable or changes format."""
    if not sources or len(sources) > 20:
        raise ValueError("Configure between one and twenty sources")
    identifiers = [source["source_id"] for source in sources]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Source IDs must be unique")
    result = {key: 0 for key in COUNT_FIELDS}
    result["sources"] = []
    for source in sources:
        try:
            if source["format"] in ("club_sites", "instagram_browser"):
                if source["format"] == "club_sites":
                    from scripts.club_sites import check as batch_check
                else:
                    from scripts.instagram_monitor import check as batch_check
                counts = batch_check(client, app_url, source["source_id"], token,
                                     private_backend_host, source.get("options") or {})
            else:
                counts = check_source(client, source["url"], app_url, source["source_id"], token,
                                      source["format"], int(source.get("lookahead_days", 60)),
                                      private_backend_host, source.get("options"))
            status = "succeeded" if not counts["failed"] else "failed"
            outcome = {"source_id": source["source_id"], "status": status, **counts}
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            error = f"HTTP {exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError) else type(exc).__name__
            outcome = {"source_id": source["source_id"], "status": "failed", "error": error,
                       **{key: 0 for key in COUNT_FIELDS}}
            outcome["failed"] = 1
        for key in COUNT_FIELDS:
            result[key] += outcome[key]
        result["sources"].append(outcome)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", choices=("public", "instagram"), default="public")
    args = parser.parse_args()
    load_dotenv()
    try:
        with httpx.Client(timeout=30) as client:
            manifest_path = os.environ.get("MARITIME_SOURCES_FILE", "")
            if manifest_path:
                manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
                selected = [s for s in manifest["sources"] if
                            (s["format"] == "instagram_browser") == (args.group == "instagram")]
                result = check_sources(client, selected, os.environ.get("APP_BASE_URL", ""),
                                       os.environ.get("SOURCE_INGEST_TOKEN", ""),
                                       os.environ.get("MARITIME_PRIVATE_BACKEND_HOST", ""))
            else:
                result = check_source(
                    client,
                    os.environ.get("MARITIME_FEED_URL", ""),
                    os.environ.get("APP_BASE_URL", ""),
                    os.environ.get("MARITIME_SOURCE_ID", "src-demo-feed"),
                    os.environ.get("SOURCE_INGEST_TOKEN", ""),
                    os.environ.get("MARITIME_FEED_FORMAT", "json"),
                    int(os.environ.get("MARITIME_LOOKAHEAD_DAYS", "60")),
                    os.environ.get("MARITIME_PRIVATE_BACKEND_HOST", ""),
                )
    except httpx.HTTPStatusError as exc:
        print(f"Feed check failed: HTTP {exc.response.status_code}", file=stderr)
        return 1
    except (httpx.RequestError, ValueError, OSError, KeyError, TypeError) as exc:
        print(f"Feed check failed: {type(exc).__name__}", file=stderr)
        return 1
    print(json.dumps(result))
    return int(result["failed"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
