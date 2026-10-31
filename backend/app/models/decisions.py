"""Validated decision records, their evidence, human reviews and audit history.

A row here exists only after backend validation. AI output that fails validation is never stored as a decision.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

TZ = DateTime(timezone=True)


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    topic: Mapped[str] = mapped_column(String(200))
    problem: Mapped[Optional[str]] = mapped_column(Text)
    decision: Mapped[Optional[str]] = mapped_column(String(500))  # None while unresolved
    status: Mapped[str] = mapped_column(String(20))  # accepted|rejected|unresolved|deferred|superseded
    # explicit: authoritative statement in the sources; inferred: implied (e.g. merged) but never stated;
    # human_confirmed: settled by an authorised reviewer; unresolved: no authoritative resolution.
    determination: Mapped[str] = mapped_column(String(20))
    verification_state: Mapped[str] = mapped_column(String(20))
    conflict_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
    superseded_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("decisions.id", ondelete="SET NULL"))
    created_by: Mapped[str] = mapped_column(String(100))  # "extractor:<model>" or "github:<login>"
    validation_notes: Mapped[List[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now(), onupdate=func.now())


class DecisionAlternative(Base):
    __tablename__ = "decision_alternatives"

    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30))
    proposed_status: Mapped[str] = mapped_column(String(30))  # what the extractor claimed, kept for audit
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    verification_state: Mapped[str] = mapped_column(String(20))


class DecisionEvidence(Base):
    """One claim-to-source link. Unsupported links are kept (flagged) so nothing is silently dropped."""

    __tablename__ = "decision_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id", ondelete="CASCADE"), index=True)
    claim_type: Mapped[str] = mapped_column(String(20))  # resolution|reason|alternative|rejection|position
    claim_text: Mapped[str] = mapped_column(Text)
    alternative: Mapped[Optional[str]] = mapped_column(String(200))
    stance: Mapped[Optional[str]] = mapped_column(String(10))  # support|oppose|neutral, for positions
    is_explicit: Mapped[bool] = mapped_column(Boolean, default=True)
    source_id: Mapped[str] = mapped_column(String(80))  # as cited by the extractor
    source_kind: Mapped[Optional[str]] = mapped_column(String(20))
    source_db_id: Mapped[Optional[int]] = mapped_column(Integer)
    html_url: Mapped[Optional[str]] = mapped_column(String(500))  # the stored original GitHub URL
    author_login: Mapped[Optional[str]] = mapped_column(String(100))
    author_association: Mapped[Optional[str]] = mapped_column(String(30))
    quote: Mapped[Optional[str]] = mapped_column(Text)  # text verified to exist in the stored source
    verification_state: Mapped[str] = mapped_column(String(20))
    flags: Mapped[List[str]] = mapped_column(JSONB, default=list)


class DecisionReview(Base):
    __tablename__ = "decision_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id", ondelete="CASCADE"), index=True)
    reviewer_login: Mapped[str] = mapped_column(String(100))
    reviewer_permission: Mapped[str] = mapped_column(String(20))  # verified with GitHub at review time
    action: Mapped[str] = mapped_column(String(20))  # resolve|keep_unresolved|supersede
    outcome_status: Mapped[str] = mapped_column(String(20))
    selected_alternative: Mapped[Optional[str]] = mapped_column(String(200))
    explanation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())


class DecisionEvent(Base):
    """Append-only audit log. `snapshot` is the full decision before the change."""

    __tablename__ = "decision_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id", ondelete="CASCADE"), index=True)
    event: Mapped[str] = mapped_column(String(30))  # created|reviewed|superseded
    actor: Mapped[str] = mapped_column(String(100))
    snapshot: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    details: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())
