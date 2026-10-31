"""Raw GitHub data, stored as GitHub returned it, with stable IDs, URLs, authors and timestamps.

Nothing in these tables is AI output. Decisions extracted later must cite rows from here.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

TZ = DateTime(timezone=True)


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    node_id: Mapped[str] = mapped_column(String(64))
    owner: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100))
    full_name: Mapped[str] = mapped_column(String(201), index=True)
    html_url: Mapped[str] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text)
    default_branch: Mapped[str] = mapped_column(String(255))
    language: Mapped[Optional[str]] = mapped_column(String(100))
    license_spdx: Mapped[Optional[str]] = mapped_column(String(100))
    stars: Mapped[int] = mapped_column(Integer, default=0)
    forks: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    has_issues: Mapped[bool] = mapped_column(Boolean, default=True)
    has_discussions: Mapped[bool] = mapped_column(Boolean, default=False)
    gh_created_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    gh_pushed_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    connected_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    # Totals as GitHub reports them (open/closed issues, PRs, commits, discussions), refreshed every sync.
    stats: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    # Per-stage "fetched everything updated up to" timestamps, for incremental sync.
    sync_cursors: Mapped[Dict[str, str]] = mapped_column(JSONB, default=dict)


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|completed|partial|failed
    stage: Mapped[str] = mapped_column(String(40), default="queued")
    full: Mapped[bool] = mapped_column(Boolean, default=False)
    progress: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    errors: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    finished_at: Mapped[Optional[datetime]] = mapped_column(TZ)


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (UniqueConstraint("repository_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    github_id: Mapped[int] = mapped_column(BigInteger)
    node_id: Mapped[str] = mapped_column(String(64))
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[Optional[str]] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20))
    state_reason: Mapped[Optional[str]] = mapped_column(String(30))
    author_login: Mapped[Optional[str]] = mapped_column(String(100))
    author_association: Mapped[Optional[str]] = mapped_column(String(30))
    labels: Mapped[List[str]] = mapped_column(JSONB, default=list)
    comments_count: Mapped[int] = mapped_column(Integer, default=0)
    html_url: Mapped[str] = mapped_column(String(400))
    gh_created_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    gh_updated_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    gh_closed_at: Mapped[Optional[datetime]] = mapped_column(TZ)


class PullRequest(Base):
    __tablename__ = "pull_requests"
    __table_args__ = (UniqueConstraint("repository_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    github_id: Mapped[int] = mapped_column(BigInteger)
    node_id: Mapped[str] = mapped_column(String(64))
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[Optional[str]] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20))
    draft: Mapped[bool] = mapped_column(Boolean, default=False)
    author_login: Mapped[Optional[str]] = mapped_column(String(100))
    author_association: Mapped[Optional[str]] = mapped_column(String(30))
    labels: Mapped[List[str]] = mapped_column(JSONB, default=list)
    base_ref: Mapped[Optional[str]] = mapped_column(String(255))
    head_ref: Mapped[Optional[str]] = mapped_column(String(255))
    head_sha: Mapped[Optional[str]] = mapped_column(String(40))
    merge_commit_sha: Mapped[Optional[str]] = mapped_column(String(40))
    html_url: Mapped[str] = mapped_column(String(400))
    gh_created_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    gh_updated_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    gh_closed_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    gh_merged_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    # gh_updated_at value at the time reviews and files were last fetched; equal means nothing changed.
    details_updated_at: Mapped[Optional[datetime]] = mapped_column(TZ)


class PullRequestFile(Base):
    __tablename__ = "pull_request_files"
    __table_args__ = (UniqueConstraint("pull_request_id", "filename"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(1024))
    previous_filename: Mapped[Optional[str]] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(20))
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)
    blob_sha: Mapped[Optional[str]] = mapped_column(String(40))


class Discussion(Base):
    __tablename__ = "discussions"
    __table_args__ = (UniqueConstraint("repository_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    github_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    node_id: Mapped[str] = mapped_column(String(64))
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(100))
    author_login: Mapped[Optional[str]] = mapped_column(String(100))
    answer_node_id: Mapped[Optional[str]] = mapped_column(String(64))
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
    html_url: Mapped[str] = mapped_column(String(400))
    gh_created_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    gh_updated_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    gh_closed_at: Mapped[Optional[datetime]] = mapped_column(TZ)


class Comment(Base):
    """Every message attached to an issue, pull request or discussion, in one table.

    kind: issue_comment | review | review_comment | discussion_comment | discussion_reply
    parent_kind: issue | pull_request | discussion
    """

    __tablename__ = "comments"
    __table_args__ = (UniqueConstraint("repository_id", "node_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    github_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    node_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(30))
    parent_kind: Mapped[str] = mapped_column(String(20))
    parent_number: Mapped[int] = mapped_column(Integer, index=True)
    author_login: Mapped[Optional[str]] = mapped_column(String(100))
    author_association: Mapped[Optional[str]] = mapped_column(String(30))
    body: Mapped[Optional[str]] = mapped_column(Text)
    review_state: Mapped[Optional[str]] = mapped_column(String(30))  # APPROVED, CHANGES_REQUESTED, ...
    path: Mapped[Optional[str]] = mapped_column(String(1024))
    line: Mapped[Optional[int]] = mapped_column(Integer)
    commit_sha: Mapped[Optional[str]] = mapped_column(String(40))
    in_reply_to: Mapped[Optional[str]] = mapped_column(String(64))  # parent comment id (REST id or node id)
    html_url: Mapped[str] = mapped_column(String(400))
    gh_created_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    gh_updated_at: Mapped[Optional[datetime]] = mapped_column(TZ)


class Commit(Base):
    __tablename__ = "commits"
    __table_args__ = (UniqueConstraint("repository_id", "sha"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    sha: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    author_login: Mapped[Optional[str]] = mapped_column(String(100))
    author_name: Mapped[Optional[str]] = mapped_column(String(200))
    author_email: Mapped[Optional[str]] = mapped_column(String(320))
    committer_login: Mapped[Optional[str]] = mapped_column(String(100))
    parents: Mapped[List[str]] = mapped_column(JSONB, default=list)
    html_url: Mapped[str] = mapped_column(String(400))
    authored_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    committed_at: Mapped[Optional[datetime]] = mapped_column(TZ)


class SourceFile(Base):
    __tablename__ = "source_files"
    __table_args__ = (UniqueConstraint("repository_id", "path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(1024))
    blob_sha: Mapped[str] = mapped_column(String(40))
    size: Mapped[int] = mapped_column(Integer)
    language: Mapped[Optional[str]] = mapped_column(String(30))
    priority: Mapped[int] = mapped_column(Integer)
    content: Mapped[Optional[str]] = mapped_column(Text)
    skipped_reason: Mapped[Optional[str]] = mapped_column(String(40))
    html_url: Mapped[str] = mapped_column(String(1400))
    fetched_at: Mapped[datetime] = mapped_column(TZ, server_default=func.now())
