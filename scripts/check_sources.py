"""Check one approved club feed and submit its announcements to Club Alerts."""

import json
import os
from datetime import datetime, timezone
from sys import stderr

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field, HttpUrl

MAX_FEED_BYTES = 256 * 1024
MAX_FLYER_BYTES = 5 * 1024 * 1024


class Listing(BaseModel):
    external_id: str = Field(min_length=1, max_length=200)
    source_url: HttpUrl
    caption: str = Field(default="", max_length=20_000)
    flyer_url: HttpUrl | None = None


class Feed(BaseModel):
    events: list[Listing] = Field(max_length=50)


def _service_url(value: str) -> httpx.URL:
    try:
        url = httpx.URL(value)
    except httpx.InvalidURL as exc:
        raise ValueError("Invalid service URL") from exc
    loopback = url.host in ("localhost", "127.0.0.1", "::1")
    if not url.host or url.userinfo or not (url.scheme == "https" or (loopback and url.scheme == "http")):
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


def check_source(client: httpx.Client, feed_url: str, app_url: str, source_id: str, token: str) -> dict:
    if not source_id or not token:
        raise ValueError("Set MARITIME_SOURCE_ID and SOURCE_INGEST_TOKEN")
    feed_endpoint = _service_url(feed_url)
    intake = _service_url(app_url).join("/api/intake")
    headers = {"Authorization": f"Bearer {token}"}
    feed = Feed.model_validate_json(_download(client, feed_endpoint, MAX_FEED_BYTES))
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
        try:
            if event.flyer_url:
                flyer_url = _service_url(str(event.flyer_url))
                if (flyer_url.scheme, flyer_url.netloc) != (feed_endpoint.scheme, feed_endpoint.netloc):
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


def main() -> int:
    load_dotenv()
    try:
        with httpx.Client(timeout=30) as client:
            result = check_source(
                client,
                os.environ.get("MARITIME_FEED_URL", ""),
                os.environ.get("APP_BASE_URL", ""),
                os.environ.get("MARITIME_SOURCE_ID", "src-demo-feed"),
                os.environ.get("SOURCE_INGEST_TOKEN", ""),
            )
    except httpx.HTTPStatusError as exc:
        print(f"Feed check failed: HTTP {exc.response.status_code}", file=stderr)
        return 1
    except (httpx.RequestError, ValueError) as exc:
        print(f"Feed check failed: {type(exc).__name__}", file=stderr)
        return 1
    print(json.dumps(result))
    return int(result["failed"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
