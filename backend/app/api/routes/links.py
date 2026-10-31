from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import Decision, DecisionCodeLink, Repository, SourceLink
from app.schemas.links import CodeLinkOut, CodeMap, FileDecision, LinkOut, RecordRef, RelatedGraph
from app.services.impact.code_map import map_decision
from app.services.linking.detector import rebuild_links
from app.services.linking.history import related_graph

router = APIRouter(tags=["links"])


def _repo(db: Session, repository_id: int) -> Repository:
    repo = db.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found.")
    return repo


def _decision(db: Session, decision_id: int) -> Decision:
    d = db.get(Decision, decision_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Decision not found.")
    return d


@router.post("/repositories/{repository_id}/links/rebuild")
def rebuild(repository_id: int, db: Session = Depends(get_db)) -> dict:
    counts = rebuild_links(db, _repo(db, repository_id))
    db.commit()
    return counts


@router.get("/repositories/{repository_id}/links", response_model=List[LinkOut])
def list_links(
    repository_id: int,
    kind: Optional[str] = Query(None, pattern="^(issue|pull_request|discussion|commit)$"),
    record_id: Optional[int] = None,
    verification_status: Optional[str] = Query(None, pattern="^(verified|possible)$"),
    db: Session = Depends(get_db),
) -> List[LinkOut]:
    _repo(db, repository_id)
    q = select(SourceLink).where(SourceLink.repository_id == repository_id)
    if kind and record_id is not None:
        q = q.where(or_((SourceLink.source_kind == kind) & (SourceLink.source_id == record_id),
                        (SourceLink.target_kind == kind) & (SourceLink.target_id == record_id)))
    if verification_status:
        q = q.where(SourceLink.verification_status == verification_status)
    return [
        LinkOut(source=RecordRef(kind=l.source_kind, id=l.source_id), target=RecordRef(kind=l.target_kind, id=l.target_id),
                relation=l.relation, signal=l.signal, verification_status=l.verification_status,
                confidence=l.confidence, evidence=l.evidence)
        for l in db.scalars(q.order_by(SourceLink.verification_status.desc(), SourceLink.confidence.desc()).limit(500))
    ]


@router.get("/decisions/{decision_id}/related", response_model=RelatedGraph)
def related(decision_id: int, db: Session = Depends(get_db)) -> RelatedGraph:
    return RelatedGraph.model_validate(related_graph(db, _decision(db, decision_id)))


@router.get("/decisions/{decision_id}/code", response_model=CodeMap)
def code(decision_id: int, db: Session = Depends(get_db)) -> CodeMap:
    """Recomputed on every request so it reflects the latest sync."""
    result = map_decision(db, _decision(db, decision_id))
    return CodeMap(
        decision_id=result["decision_id"], message=result["message"], notes=result["notes"],
        verified=[CodeLinkOut.model_validate(r) for r in result["verified"]],
        possible=[CodeLinkOut.model_validate(r) for r in result["possible"]],
    )


@router.get("/repositories/{repository_id}/files/decisions", response_model=List[FileDecision])
def decisions_for_file(repository_id: int, path: str = Query(..., min_length=1, max_length=1024),
                       db: Session = Depends(get_db)) -> List[FileDecision]:
    """Decisions whose implementation touched this file (under its old or current name)."""
    _repo(db, repository_id)
    rows = db.execute(
        select(DecisionCodeLink, Decision)
        .join(Decision, DecisionCodeLink.decision_id == Decision.id)
        .where(Decision.repository_id == repository_id,
               or_(DecisionCodeLink.path == path, DecisionCodeLink.current_path == path))
        .order_by(DecisionCodeLink.link_status.desc(), Decision.id)
    )
    out: dict = {}
    for l, d in rows:  # one entry per decision; rows are ordered so a verified link wins over a possible one
        out.setdefault(d.id, FileDecision(
            decision_id=d.id, topic=d.topic, status=d.status, determination=d.determination,
            link_status=l.link_status, pr_number=l.pr_number, pr_url=l.pr_url, path=l.path,
            current_path=l.current_path))
    return list(out.values())
