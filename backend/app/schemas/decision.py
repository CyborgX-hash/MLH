from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    claim_type: str
    claim_text: str
    alternative: Optional[str]
    stance: Optional[str]
    is_explicit: bool
    source_id: str
    source_kind: Optional[str]
    html_url: Optional[str]
    author_login: Optional[str]
    author_association: Optional[str]
    quote: Optional[str]
    verification_state: str
    flags: List[str]


class AlternativeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    status: str
    proposed_status: str
    rejection_reason: Optional[str]
    verification_state: str


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reviewer_login: str
    reviewer_permission: str
    action: str
    outcome_status: str
    selected_alternative: Optional[str]
    explanation: str
    created_at: datetime


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event: str
    actor: str
    snapshot: Dict[str, Any]
    details: Dict[str, Any]
    created_at: datetime


class DecisionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    repository_id: int
    topic: str
    problem: Optional[str]
    decision: Optional[str]
    status: str
    determination: str
    verification_state: str
    conflict_detected: bool
    requires_human_review: bool
    superseded_by_id: Optional[int]
    created_by: str
    created_at: datetime
    updated_at: datetime


class DecisionListItem(DecisionSummary):
    alternatives: List["AlternativeOut"] = []
    evidence_count: int = 0
    verified_evidence: int = 0
    sources: List[Dict[str, Any]] = []  # threads it was discussed in: kind, number, title, url
    participants: List[Dict[str, Any]] = []  # login, association


class DecisionOut(DecisionSummary):
    validation_notes: List[str]
    alternatives: List[AlternativeOut] = []
    evidence: List[EvidenceOut] = []
    reviews: List[ReviewOut] = []
    history: List[EventOut] = []


class ValidationReport(BaseModel):
    topic: str
    decision: Optional[str]
    decision_status: str
    determination: str
    conflict_detected: bool
    requires_human_review: bool
    verification_state: str
    alternatives: List[AlternativeOut]
    evidence: List[EvidenceOut]
    notes: List[str]
    would_create: bool


class RejectedAlternative(BaseModel):
    name: str = Field(..., max_length=200)
    reason: Optional[str] = Field(None, max_length=1000)


class ReviewRequest(BaseModel):
    outcome_status: Literal["accepted", "rejected", "deferred", "unresolved"]
    selected_alternative: Optional[str] = Field(None, max_length=200)
    decision: Optional[str] = Field(None, max_length=500)
    rejected_alternatives: List[RejectedAlternative] = Field(default_factory=list)
    explanation: str = Field(..., min_length=10, max_length=4000)


class SupersedeRequest(BaseModel):
    superseded_by_id: int
    explanation: str = Field(..., min_length=10, max_length=4000)
