"""Candidate extraction output: what an AI extractor may *propose*.

Nothing here is trusted. The evidence validator checks every reference against stored GitHub data and
the backend status rules decide the final status. A candidate never becomes a decision on its own.

Evidence references use DeciTrace source IDs: "<kind>:<id>" where kind is comment, issue,
pull_request, discussion or commit, and id is the DeciTrace database id given to the extractor.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

AlternativeStatus = Literal["selected", "rejected", "considered_not_selected", "proposed", "deferred"]
DecisionStatus = Literal["accepted", "rejected", "unresolved", "deferred"]


class EvidenceRef(BaseModel):
    source_id: str = Field(..., max_length=80, examples=["comment:102"])
    quote: Optional[str] = Field(None, max_length=2000, description="Text the extractor says appears in the source")
    url: Optional[str] = Field(None, max_length=500, description="URL the extractor claims; never trusted")


class CandidateAlternative(BaseModel):
    name: str = Field(..., max_length=200)
    status: AlternativeStatus = "proposed"
    rejection_reason: Optional[str] = Field(None, max_length=1000)
    evidence: List[EvidenceRef] = Field(default_factory=list, max_length=20)
    rejection_evidence: List[EvidenceRef] = Field(default_factory=list, max_length=20)


class CandidateReason(BaseModel):
    reason: str = Field(..., max_length=1000)
    alternative: Optional[str] = Field(None, max_length=200, description="Alternative this reason is about")
    is_explicit: bool = True
    evidence: List[EvidenceRef] = Field(default_factory=list, max_length=20)


class CandidatePosition(BaseModel):
    """One participant's stated stance. Kept even when it disagrees with the outcome."""

    alternative: str = Field(..., max_length=200)
    stance: Literal["support", "oppose", "neutral"]
    evidence: EvidenceRef


class CandidateDecision(BaseModel):
    topic: str = Field(..., max_length=200)
    problem: Optional[str] = Field(None, max_length=2000)
    decision: Optional[str] = Field(None, max_length=500)
    decision_status: DecisionStatus = "unresolved"
    is_explicit: bool = False
    # Bounded so one request cannot make the validator do unbounded work.
    alternatives: List[CandidateAlternative] = Field(default_factory=list, max_length=30)
    reasoning: List[CandidateReason] = Field(default_factory=list, max_length=60)
    positions: List[CandidatePosition] = Field(default_factory=list, max_length=100)
    resolution_evidence: List[EvidenceRef] = Field(
        default_factory=list, max_length=20, description="The statement(s) that establish the final decision, if any"
    )
    conflict_detected: bool = False
    requires_human_review: bool = False
    model: Optional[str] = Field(None, max_length=100, description="Model that produced the candidate")
