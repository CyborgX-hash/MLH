"""ORM models. Import every model module here so Alembic sees it in Base.metadata."""
from app.db.base import Base
from app.models.decisions import Decision, DecisionAlternative, DecisionEvent, DecisionEvidence, DecisionReview
from app.models.knowledge import KnowledgeChunk
from app.models.links import DecisionCodeLink, SourceLink
from app.models.github import (
    Comment,
    Commit,
    Discussion,
    Issue,
    PullRequest,
    PullRequestFile,
    Repository,
    SourceFile,
    SyncJob,
)

__all__ = [
    "Decision", "DecisionAlternative", "DecisionEvent", "DecisionEvidence", "DecisionReview",
    "DecisionCodeLink", "SourceLink", "KnowledgeChunk",
    "Base", "Comment", "Commit", "Discussion", "Issue", "PullRequest", "PullRequestFile", "Repository",
    "SourceFile", "SyncJob",
]
