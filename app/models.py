from typing import Literal, Optional

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    field: str
    excerpt: str


class Candidate(BaseModel):
    """Structured event fields extracted from a flyer or caption. Unknown values stay None."""
    organizer_slug: Optional[str] = None
    title: Optional[str] = None
    local_date: Optional[str] = None      # YYYY-MM-DD, America/Vancouver
    local_start: Optional[str] = None     # HH:MM, 24h
    local_end: Optional[str] = None
    timezone: str = "America/Vancouver"
    venue: Optional[str] = None
    cost_status: Literal["free", "paid", "unknown"] = "unknown"
    beginner_friendly: Optional[bool] = None
    topics: list[str] = Field(default_factory=list)
    rsvp_url: Optional[str] = None
    evidence: list[Evidence] = Field(default_factory=list)


class IntakeRequest(BaseModel):
    source_id: str
    external_id: str
    source_url: Optional[str] = None
    observed_at: Optional[str] = None
    caption: Optional[str] = None


class SubscribeRequest(BaseModel):
    email: str
    topics: list[str] = Field(default_factory=list)
    want_free: bool = False
    want_beginner: bool = False
    after_4pm: bool = False


class ResolveRequest(BaseModel):
    decision: Literal["link", "separate", "confirm", "reject"]
    expected_revision: Optional[int] = None
    reviewer: str = "team"


class ClaimRequest(BaseModel):
    subscriber_id: str
    event_id: str
    revision: int
    kind: Literal["new_event", "correction"]


class ResultRequest(BaseModel):
    claim_token: str
    outcome: Literal["accepted", "retryable", "terminal"]
    provider_msg_id: Optional[str] = None
