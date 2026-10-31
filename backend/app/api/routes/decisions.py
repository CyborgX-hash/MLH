from typing import Callable, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import Decision, DecisionAlternative, DecisionEvent, DecisionEvidence, DecisionReview, Repository
from app.schemas.decision import (
    AlternativeOut, DecisionOut, DecisionSummary, EventOut, EvidenceOut, ReviewOut, ReviewRequest, SupersedeRequest,
    ValidationReport,
)
from app.schemas.extraction import CandidateDecision
from app.services.evidence.authority import Reviewer, verify_reviewer
from app.services.evidence.records import ReviewError, create_decision, review_decision, supersede_decision
from app.services.evidence.validator import Result, validate
from app.services.github.errors import GitHubError, Unauthorized

router = APIRouter(tags=["decisions"])
ReviewerVerifier = Callable[[str, str, str], Reviewer]


def get_reviewer_verifier() -> ReviewerVerifier:
    return verify_reviewer


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


def _report(r: Result) -> ValidationReport:
    return ValidationReport(
        topic=r.topic, decision=r.decision, decision_status=r.status, determination=r.determination,
        conflict_detected=r.conflict_detected, requires_human_review=r.requires_human_review,
        verification_state=r.verification_state, notes=r.notes, would_create=r.can_create,
        alternatives=[AlternativeOut(name=a.name, status=a.status, proposed_status=a.proposed_status,
                                     rejection_reason=a.rejection_reason, verification_state=a.verification_state)
                      for a in r.alternatives],
        evidence=[EvidenceOut(
            claim_type=c.claim_type, claim_text=c.claim_text, alternative=c.alternative, stance=c.stance,
            is_explicit=c.is_explicit, source_id=c.ref.source_id, source_kind=c.source.kind if c.source else None,
            html_url=c.source.html_url if c.source else None, author_login=c.source.author_login if c.source else None,
            author_association=c.source.author_association if c.source else None, quote=c.quote,
            verification_state=c.state, flags=c.flags) for c in r.checks],
    )


def _out(db: Session, d: Decision) -> DecisionOut:
    def rows(model, order):
        return db.scalars(select(model).where(model.decision_id == d.id).order_by(order)).all()

    return DecisionOut(
        **DecisionSummary.model_validate(d).model_dump(),
        validation_notes=d.validation_notes or [],
        alternatives=[AlternativeOut.model_validate(a) for a in rows(DecisionAlternative, DecisionAlternative.id)],
        evidence=[EvidenceOut.model_validate(e) for e in rows(DecisionEvidence, DecisionEvidence.id)],
        reviews=[ReviewOut.model_validate(r) for r in rows(DecisionReview, DecisionReview.id)],
        history=[EventOut.model_validate(e) for e in rows(DecisionEvent, DecisionEvent.id)],
    )


def _reviewer(
    db: Session, d: Decision, token: Optional[str], verifier: ReviewerVerifier
) -> Reviewer:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Send your GitHub token in X-GitHub-Token to prove who you are.")
    repo = db.get(Repository, d.repository_id)
    try:
        return verifier(token, repo.owner, repo.name)
    except Unauthorized:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "GitHub rejected that token.")
    except GitHubError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not verify the reviewer with GitHub: {exc}")


@router.post("/repositories/{repository_id}/decisions/validate", response_model=ValidationReport)
def validate_candidate(repository_id: int, cand: CandidateDecision, db: Session = Depends(get_db)) -> ValidationReport:
    """Dry run: shows exactly what validation would do with a candidate, stores nothing."""
    return _report(validate(db, _repo(db, repository_id), cand))


@router.post("/repositories/{repository_id}/decisions", response_model=DecisionOut, status_code=status.HTTP_201_CREATED)
def create(repository_id: int, cand: CandidateDecision, db: Session = Depends(get_db)) -> DecisionOut:
    d, result = create_decision(db, _repo(db, repository_id), cand)
    if d is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"message": "No cited evidence could be verified; no decision was recorded.",
             "report": _report(result).model_dump()},
        )
    return _out(db, d)


@router.get("/repositories/{repository_id}/decisions", response_model=List[DecisionSummary])
def list_decisions(repository_id: int, status_filter: Optional[str] = None, db: Session = Depends(get_db)):
    _repo(db, repository_id)
    q = select(Decision).where(Decision.repository_id == repository_id)
    if status_filter:
        q = q.where(Decision.status == status_filter)
    return db.scalars(q.order_by(Decision.requires_human_review.desc(), Decision.id.desc())).all()


@router.get("/decisions/{decision_id}", response_model=DecisionOut)
def get_decision(decision_id: int, db: Session = Depends(get_db)) -> DecisionOut:
    return _out(db, _decision(db, decision_id))


@router.post("/decisions/{decision_id}/reviews", response_model=DecisionOut)
def review(
    decision_id: int,
    body: ReviewRequest,
    db: Session = Depends(get_db),
    x_github_token: Optional[str] = Header(None),
    verifier: ReviewerVerifier = Depends(get_reviewer_verifier),
) -> DecisionOut:
    d = _decision(db, decision_id)
    reviewer = _reviewer(db, d, x_github_token, verifier)
    try:
        review_decision(db, d, reviewer, body.outcome_status, body.explanation, body.selected_alternative,
                        body.decision, [r.model_dump() for r in body.rejected_alternatives])
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    except ReviewError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    return _out(db, d)


@router.post("/decisions/{decision_id}/supersede", response_model=DecisionOut)
def supersede(
    decision_id: int,
    body: SupersedeRequest,
    db: Session = Depends(get_db),
    x_github_token: Optional[str] = Header(None),
    verifier: ReviewerVerifier = Depends(get_reviewer_verifier),
) -> DecisionOut:
    old = _decision(db, decision_id)
    new = _decision(db, body.superseded_by_id)
    reviewer = _reviewer(db, old, x_github_token, verifier)
    try:
        supersede_decision(db, old, new, reviewer, body.explanation)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    except ReviewError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    return _out(db, old)
