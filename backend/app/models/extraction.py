"""Bookkeeping for AI decision extraction runs. Decisions themselves live in decisions.py."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

TZ = DateTime(timezone=True)


class ExtractionJob(Base):
    __tablename__ = "extraction_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|completed|partial|failed
    model: Mapped[str] = mapped_column(String(100))
    threads_total: Mapped[int] = mapped_column(Integer, default=0)
    threads_done: Mapped[int] = mapped_column(Integer, default=0)
    candidates: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[int] = mapped_column(Integer, default=0)  # new validated decisions
    merged: Mapped[int] = mapped_column(Integer, default=0)  # added to an existing decision
    refused: Mapped[int] = mapped_column(Integer, default=0)  # no verifiable evidence: not recorded
    errors: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(TZ)


class ExtractedThread(Base):
    """Which thread was extracted, from which version of its content, and what came out."""

    __tablename__ = "extracted_threads"
    __table_args__ = (UniqueConstraint("repository_id", "record_kind", "record_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    record_kind: Mapped[str] = mapped_column(String(20))
    record_id: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(40))  # unchanged thread => not extracted again
    model: Mapped[str] = mapped_column(String(100))
    outcome: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    extracted_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())
