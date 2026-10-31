"""Searchable knowledge base: text chunks with full-text vectors and (optional) pgvector embeddings."""
from datetime import datetime
from typing import List, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeChunk(Base):
    """kind: decision | issue | pull_request | discussion | comment | commit | file.

    `embedding` has no fixed dimension so the embedding model can be swapped; searches only compare rows
    produced by the same `embed_model`.
    """

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("repository_id", "kind", "ref_id", "chunk_no"),
        Index("ix_knowledge_chunks_tsv", "tsv", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    ref_id: Mapped[int] = mapped_column(Integer)  # DeciTrace id of the decision / record / comment / file
    chunk_no: Mapped[int] = mapped_column(Integer, default=0)
    parent_kind: Mapped[Optional[str]] = mapped_column(String(20))  # for comments: issue | pull_request | discussion
    number: Mapped[Optional[int]] = mapped_column(Integer)  # issue/PR/discussion number (parent's for comments)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(1400))
    author_login: Mapped[Optional[str]] = mapped_column(String(100))
    decision_status: Mapped[Optional[str]] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(40))
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector())
    embed_model: Mapped[Optional[str]] = mapped_column(String(100))
    tsv = mapped_column(TSVECTOR, Computed("to_tsvector('english', coalesce(title, '') || ' ' || text)", persisted=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
