from datetime import date
from typing import Literal, Optional

from pydantic import AwareDatetime, BaseModel, Field


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
    perks: list[str] = Field(default_factory=list)  # subset of extract.PERKS, only when stated
    audience: list[str] = Field(default_factory=list)  # extract.AUDIENCES; [] = not stated
    rsvp_url: Optional[str] = None
    evidence: list[Evidence] = Field(default_factory=list)


class IntakeRequest(BaseModel):
    source_id: str
    external_id: str
    source_url: Optional[str] = None
    observed_at: Optional[AwareDatetime] = None
    caption: Optional[str] = None
    candidate: Optional[Candidate] = None


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


# ---------------------------------------------------------------- accounts

GENDERS = ("woman", "man", "non-binary", "self-describe", "prefer-not")


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)


class ProfileRequest(BaseModel):
    """Answers from the account setup flow. Everything except interests may be skipped."""
    birthday: Optional[date] = None
    major: Optional[str] = Field(default=None, max_length=80)
    gender: Optional[Literal["woman", "man", "non-binary", "self-describe", "prefer-not"]] = None
    gender_detail: Optional[str] = Field(default=None, max_length=40)
    interests: list[str] = Field(default_factory=list, max_length=8)
    hobbies: list[str] = Field(default_factory=list, max_length=12)
