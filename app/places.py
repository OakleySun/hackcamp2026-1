"""Turn a free-text venue ("DMP 110", "AMS Nest Great Hall") into a UBC building with coordinates.

The building list lives in fixtures/ubc_buildings.json. Matching is deliberately conservative:
an unmatched venue returns None, and the map lists that event as "not on the map" rather than
guessing a pin.
"""
from __future__ import annotations

import json
import pathlib
import re
from functools import lru_cache

BUILDINGS = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "ubc_buildings.json"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()


@lru_cache(maxsize=1)
def _index() -> list[tuple[re.Pattern, int, dict]]:
    """(pattern, specificity, place) sorted most specific first."""
    out = []
    for b in json.loads(BUILDINGS.read_text(encoding="utf-8"))["buildings"]:
        place = {"id": b["id"], "name": b["name"], "lat": b["lat"], "lng": b["lng"]}
        for alias in b["aliases"]:
            out.append((re.compile(rf"(^| ){re.escape(_norm(alias))}( |$)"), len(alias), place))
        for code in b["codes"]:
            # A building code only counts on its own or right before a room: "DMP 110", "BUCH A101".
            c = re.escape(code.lower())
            out.append((re.compile(rf"(^{c}$)|(^| ){c} ?[a-z]?[0-9]"), len(code), place))
    return sorted(out, key=lambda x: -x[1])


def locate(venue: str | None) -> dict | None:
    if not venue:
        return None
    text = _norm(venue)
    for pattern, _, place in _index():
        if pattern.search(text):
            return dict(place)
    return None
