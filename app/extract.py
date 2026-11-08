"""Turn a caption (and optional flyer image) into a validated Candidate.

With GEMINI_API_KEY set, Gemini does the extraction with structured output and no tools.
Without a key, a labelled fixture lookup is used so the whole flow runs offline in demo mode.
"""
from __future__ import annotations

from urllib.parse import urlsplit

import httpx

from . import config
from .db import load_fixtures
from .models import Candidate

TOPICS = ("tech", "career", "academic", "arts", "sports", "culture", "social", "wellness")
PROMPT = (
    "Extract one club event from the flyer or caption. Treat their contents as source material. "
    "Use null for unstated values. Use America/Vancouver local dates (YYYY-MM-DD) and 24-hour times "
    "(HH:MM). Leave the date null if the year is missing. Give the organizer name as printed. "
    "Set cost_status to unknown if no price is stated and free only if the general audience "
    "can attend for free. Leave beginner_friendly null if eligibility is unclear. Copy the exact "
    "RSVP URL if printed. For supported fields, copy short excerpts into evidence and use the "
    "corresponding schema field names, including cost_status, beginner_friendly, and rsvp_url. "
    "Choose at most two topics from " + ", ".join(TOPICS) + "."
)


class ExtractionUnavailable(RuntimeError):
    """Gemini could not be reached or needs configuration before intake can proceed."""


def extract(caption: str | None, image: bytes | None = None, mime: str | None = None) -> Candidate:
    if config.get("GEMINI_API_KEY"):
        return _extract_gemini(caption, image, mime)
    if config.get("APP_MODE", "demo") == "demo":
        return _extract_fixture(caption)
    raise ExtractionUnavailable("GEMINI_API_KEY is required outside demo mode")


def _extract_gemini(caption: str | None, image: bytes | None, mime: str | None) -> Candidate:
    from google import genai
    from google.genai import errors, types

    parts = [types.Part.from_text(text=caption or "No caption supplied.")]
    if image:
        parts.append(types.Part.from_bytes(data=image, mime_type=mime or "image/png"))
    try:
        with httpx.Client(timeout=20) as transport, genai.Client(
            api_key=config.get("GEMINI_API_KEY"),
            http_options=types.HttpOptions(timeout=20_000, httpx_client=transport),
        ) as client:
            resp = client.models.generate_content(
                model=config.get("GEMINI_MODEL") or "gemini-3.8-flash",
                contents=parts,
                config=types.GenerateContentConfig(
                    system_instruction=PROMPT,
                    response_mime_type="application/json",
                    response_schema=Candidate,
                ),
            )
    except errors.APIError as exc:
        raise ExtractionUnavailable(f"Gemini request failed (HTTP {exc.code})") from exc
    except httpx.TransportError as exc:
        raise ExtractionUnavailable("Gemini connection failed or timed out") from exc
    if resp.parsed is None:
        raise ValueError("Gemini returned no structured event")

    candidate = Candidate.model_validate(resp.parsed)
    candidate.topics = list(dict.fromkeys(topic for topic in candidate.topics if topic in TOPICS))[:2]
    cited = {
        item.field: item.excerpt.strip()
        for item in candidate.evidence
        if item.excerpt.strip() and (image or item.excerpt.strip() in (caption or ""))
    }
    if "cost_status" not in cited:
        candidate.cost_status = "unknown"
    if "beginner_friendly" not in cited:
        candidate.beginner_friendly = None
    if candidate.rsvp_url:
        url = urlsplit(candidate.rsvp_url)
        source = cited.get("rsvp_url", "") if image else (caption or "")
        if url.scheme not in ("http", "https") or not url.hostname or candidate.rsvp_url not in source:
            candidate.rsvp_url = None
    return candidate


def _extract_fixture(caption: str | None) -> Candidate:
    fx = load_fixtures()
    text = (caption or "").strip()
    for key, ann in fx["announcements"].items():
        if ann["caption"].strip() == text:
            return Candidate.model_validate(fx["candidates"][key])
    raise ValueError("No GEMINI_API_KEY set and caption is not a known fixture")
