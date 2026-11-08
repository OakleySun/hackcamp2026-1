"""Assign Quad's existing topic tags when a listing has no usable tags of its own."""

import re
from collections.abc import Iterable

TOPICS = ("tech", "career", "academic", "arts", "sports", "culture", "social", "wellness")

# Match activities and subjects, rather than generic words like “club” or “workshop”.
_SIGNALS = {
    "tech": r"hackathons?|vibe[ -]cod(?:e|ing)|coding|programming|software|git(?:hub)?|computer science|artificial intelligence|machine learning|robotics|cybersecurity|web development|business technology management",
    "career": r"career|job fairs?|networking|r[eé]sum[eé]|cover letters?|recruit(?:ing|ment)|internships?|professional development|industry panels?|start[ -]?up sprint",
    "academic": r"study (?:cafe|caf[eé]|group|session|hall)|(?:exam|midterm) (?:prep|review)|review sessions?|tutoring|thesis|research (?:talk|seminar|presentation|symposium)|academic advising|guest lectures?",
    "arts": r"calligraphy|karaoke|(?:art|film|music|dance) (?:show|workshop|festival|class)|film screenings?|concerts?|paint(?:ing| night)|pottery|poetry|open mic|photography|theatre|theater|anime",
    "sports": r"basketball|volleyball|badminton|soccer|hockey|(?:rock )?climbing|bouldering|pickleball|ultimate frisbee|intramural|esports|arena match|(?:running|hiking) (?:club|group|trip)",
    "culture": r"cultural (?:festival|celebration|night|exchange)|language exchange|lunar new year|diwali|nowruz|mid[ -]autumn|indigenous (?:culture|heritage)|pow[ -]?wow|heritage month",
    "social": r"social|mixers?|board games?|game nights?|trivia|magic:\s+the gathering|(?:meet|hang)[ -]?ups?|speed friending|drop[ -]in gathering",
    "wellness": r"wellness|mental health|meditation|mindfulness|yoga|stress (?:relief|management)|self[ -]care|peer support",
}
_PATTERNS = {tag: re.compile(rf"\b(?:{signal})\b", re.IGNORECASE) for tag, signal in _SIGNALS.items()}


def valid_topics(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value.strip().lower() for value in values if value.strip().lower() in TOPICS))[:2]


def _matches(text: str) -> list[str]:
    matches = [(match.start(), tag) for tag, pattern in _PATTERNS.items() if (match := pattern.search(text))]
    return [tag for _, tag in sorted(matches)[:2]]


def event_topics(values: Iterable[str], title: str | None, captions: Iterable[str | None] = ()) -> list[str]:
    """Keep source/extractor tags first, then check the title and structured descriptions."""
    tags = valid_topics(values) or _matches(title or "")
    if tags:
        return tags
    for caption in captions:
        # Structured feeds put description last, after metadata such as the organizer and room.
        _, _, description = (caption or "").partition("\nDescription:")
        if tags := _matches(description.strip()[:400]):
            return tags
    return []
