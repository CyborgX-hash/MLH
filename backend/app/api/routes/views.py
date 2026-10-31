from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import Decision, Repository
from app.services.history.views import graph, overview, timeline

router = APIRouter(tags=["views"])


class TimelineEvent(BaseModel):
    type: str  # proposal | argument | rejection | approval | implementation | commit | human_review | superseded
    label: str
    at: Optional[datetime]
    url: Optional[str]
    author: Optional[str]
    quote: Optional[str]
    verified: bool
    source: str


class GraphNode(BaseModel):
    id: str
    kind: str
    label: str
    url: Optional[str] = None
    title: Optional[str] = None
    status: Optional[str] = None
    determination: Optional[str] = None
    deleted: Optional[bool] = None
    original_path: Optional[str] = None


class GraphEdge(BaseModel):
    source: str
    target: str
    label: str
    status: str  # verified | possible


class DecisionGraph(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]


def _decision(db: Session, decision_id: int) -> Decision:
    d = db.get(Decision, decision_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Decision not found.")
    return d


@router.get("/repositories/{repository_id}/overview")
def repository_overview(repository_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    repo = db.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found.")
    return overview(db, repo)


@router.get("/decisions/{decision_id}/timeline", response_model=List[TimelineEvent])
def decision_timeline(decision_id: int, db: Session = Depends(get_db)):
    return timeline(db, _decision(db, decision_id))


@router.get("/decisions/{decision_id}/graph", response_model=DecisionGraph)
def decision_graph(decision_id: int, db: Session = Depends(get_db)):
    return graph(db, _decision(db, decision_id))
