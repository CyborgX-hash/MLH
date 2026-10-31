"""Links between GitHub records, and between decisions and the code that implemented them."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

TZ = DateTime(timezone=True)

RELATIONS = ("references", "discusses", "implements", "supersedes", "conflicts_with", "related_to")


class SourceLink(Base):
    """A directed relationship between two records (issue, pull_request, discussion, commit).

    verification_status is "verified" only for explicit GitHub evidence (a reference, closing keyword or
    PR/commit metadata). Shared files, shared terminology and text similarity give "possible" links only.
    """

    __tablename__ = "source_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    source_kind: Mapped[str] = mapped_column(String(20))
    source_id: Mapped[int] = mapped_column(Integer, index=True)
    target_kind: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    relation: Mapped[str] = mapped_column(String(20))
    signal: Mapped[str] = mapped_column(String(30))
    verification_status: Mapped[str] = mapped_column(String(10))  # verified | possible
    confidence: Mapped[float] = mapped_column(Float)
    evidence: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)  # snippet, url, paths, terms, score
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())


class DecisionCodeLink(Base):
    """A file changed by a pull request (or a commit) that implemented a decision."""

    __tablename__ = "decision_code_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id", ondelete="CASCADE"), index=True)
    link_status: Mapped[str] = mapped_column(String(10))  # verified | possible
    basis: Mapped[str] = mapped_column(Text)  # why this PR/commit is considered the implementation
    pull_request_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pull_requests.id", ondelete="CASCADE"))
    pr_number: Mapped[Optional[int]] = mapped_column(Integer)
    pr_url: Mapped[Optional[str]] = mapped_column(String(400))
    merged_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    commit_sha: Mapped[Optional[str]] = mapped_column(String(40))
    commit_url: Mapped[Optional[str]] = mapped_column(String(400))
    path: Mapped[Optional[str]] = mapped_column(String(1024), index=True)  # path in the implementing change
    change_type: Mapped[Optional[str]] = mapped_column(String(20))  # added|modified|renamed|removed
    current_path: Mapped[Optional[str]] = mapped_column(String(1024), index=True)  # after later renames
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    changed_after: Mapped[List[int]] = mapped_column(JSONB, default=list)  # later merged PRs touching the file
