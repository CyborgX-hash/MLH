"""Decision records: created only from validated candidates; changed only by authorised humans; fully audited."""
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Decision, DecisionAlternative, DecisionEvent, DecisionEvidence, DecisionReview, Repository
from app.schemas.extraction import CandidateDecision
from app.services.evidence.authority import Reviewer
from app.services.evidence.validator import PARTIAL, UNSUPPORTED, VERIFIED, Result, validate


class ReviewError(ValueError):
    pass


def snapshot(db: Session, d: Decision) -> Dict[str, Any]:
    alts = db.scalars(select(DecisionAlternative).where(DecisionAlternative.decision_id == d.id)).all()
    return {
        "topic": d.topic, "decision": d.decision, "status": d.status, "determination": d.determination,
        "verification_state": d.verification_state, "conflict_detected": d.conflict_detected,
        "requires_human_review": d.requires_human_review, "superseded_by_id": d.superseded_by_id,
        "alternatives": [{"name": a.name, "status": a.status, "rejection_reason": a.rejection_reason} for a in alts],
    }


def create_decision(db: Session, repo: Repository, cand: CandidateDecision) -> Tuple[Optional[Decision], Result]:
    """Validate first; store only if at least some evidence is real. Unsupported candidates are refused."""
    result = validate(db, repo, cand)
    if not result.can_create:
        return None, result
    d = Decision(
        repository_id=repo.id, topic=result.topic, problem=result.problem, decision=result.decision,
        status=result.status, determination=result.determination, verification_state=result.verification_state,
        conflict_detected=result.conflict_detected, requires_human_review=result.requires_human_review,
        created_by=f"extractor:{cand.model or 'unknown'}", validation_notes=result.notes,
    )
    db.add(d)
    db.flush()
    for a in result.alternatives:
        db.add(DecisionAlternative(decision_id=d.id, name=a.name, status=a.status, proposed_status=a.proposed_status,
                                   rejection_reason=a.rejection_reason, verification_state=a.verification_state))
    for c in result.checks:  # unsupported checks are stored too, flagged, so nothing disappears silently
        s = c.source
        db.add(DecisionEvidence(
            decision_id=d.id, claim_type=c.claim_type, claim_text=c.claim_text, alternative=c.alternative,
            stance=c.stance, is_explicit=c.is_explicit, source_id=c.ref.source_id,
            source_kind=s.kind if s else None, source_db_id=s.db_id if s else None,
            html_url=s.html_url if s else None, author_login=s.author_login if s else None,
            author_association=s.author_association if s else None, quote=c.quote,
            verification_state=c.state, flags=c.flags,
        ))
    db.add(DecisionEvent(decision_id=d.id, event="created", actor=d.created_by, snapshot={},
                         details={"notes": result.notes}))
    db.commit()
    db.refresh(d)
    return d, result


def _evidence_state(db: Session, d: Decision) -> str:
    states = db.scalars(select(DecisionEvidence.verification_state).where(DecisionEvidence.decision_id == d.id)).all()
    if not any(s in (VERIFIED, PARTIAL) for s in states):
        return UNSUPPORTED
    return VERIFIED if all(s == VERIFIED for s in states) else PARTIAL


def review_decision(
    db: Session, d: Decision, reviewer: Reviewer, outcome_status: str, explanation: str,
    selected_alternative: Optional[str] = None, decision_text: Optional[str] = None,
    rejected: Optional[List[Dict[str, Optional[str]]]] = None,
) -> Decision:
    if not reviewer.may_resolve:
        raise PermissionError(f"@{reviewer.login} has '{reviewer.permission}' access; write access or higher is required.")
    if d.status == "superseded":
        raise ReviewError("This decision has been superseded; review the decision that replaced it.")
    alts = {a.name: a for a in db.scalars(select(DecisionAlternative).where(DecisionAlternative.decision_id == d.id))}
    if selected_alternative and selected_alternative not in alts:
        raise ReviewError(f"Unknown alternative: {selected_alternative}")
    rejected = rejected or []
    for r in rejected:
        if r.get("name") not in alts:
            raise ReviewError(f"Unknown alternative: {r.get('name')}")
        if r.get("name") == selected_alternative:
            raise ReviewError("An alternative cannot be both selected and rejected.")
    outcome_text = decision_text or selected_alternative
    if outcome_status in ("accepted", "rejected", "deferred") and not outcome_text:
        raise ReviewError("Name the decision or select an alternative.")

    before = snapshot(db, d)
    if outcome_status == "unresolved":
        d.status, d.determination, d.decision = "unresolved", "unresolved", None
        d.requires_human_review = True
    else:
        d.status, d.determination, d.decision = outcome_status, "human_confirmed", outcome_text
        d.requires_human_review = False
        rejected_names = {r["name"]: r.get("reason") for r in rejected}
        for name, a in alts.items():
            if name == selected_alternative:
                a.status, a.rejection_reason = "selected", None
            elif name in rejected_names:
                a.status, a.rejection_reason = "rejected", rejected_names[name]  # may stay None: unknown reason
            else:
                a.status, a.rejection_reason = "considered_not_selected", None
    d.verification_state = "needs_human_review" if d.requires_human_review else _evidence_state(db, d)
    db.add(DecisionReview(decision_id=d.id, reviewer_login=reviewer.login, reviewer_permission=reviewer.permission,
                          action="resolve" if outcome_status != "unresolved" else "keep_unresolved",
                          outcome_status=outcome_status, selected_alternative=selected_alternative,
                          explanation=explanation))
    db.add(DecisionEvent(decision_id=d.id, event="reviewed", actor=f"github:{reviewer.login}", snapshot=before,
                         details={"outcome_status": outcome_status, "selected_alternative": selected_alternative,
                                  "rejected": rejected, "explanation": explanation,
                                  "reviewer_permission": reviewer.permission}))
    db.commit()
    db.refresh(d)
    return d


def supersede_decision(db: Session, old: Decision, new: Decision, reviewer: Reviewer, explanation: str) -> Decision:
    if not reviewer.may_resolve:
        raise PermissionError(f"@{reviewer.login} has '{reviewer.permission}' access; write access or higher is required.")
    if old.id == new.id or old.repository_id != new.repository_id:
        raise ReviewError("A decision can only be superseded by a different decision of the same repository.")
    if new.status == "superseded":
        raise ReviewError("The replacement decision is itself superseded.")
    if old.status == "superseded":
        raise ReviewError("This decision is already superseded.")
    before = snapshot(db, old)
    old.status, old.superseded_by_id, old.requires_human_review = "superseded", new.id, False
    db.add(DecisionReview(decision_id=old.id, reviewer_login=reviewer.login, reviewer_permission=reviewer.permission,
                          action="supersede", outcome_status="superseded", selected_alternative=None,
                          explanation=explanation))
    db.add(DecisionEvent(decision_id=old.id, event="superseded", actor=f"github:{reviewer.login}", snapshot=before,
                         details={"superseded_by_id": new.id, "explanation": explanation}))
    db.add(DecisionEvent(decision_id=new.id, event="supersedes", actor=f"github:{reviewer.login}",
                         snapshot=snapshot(db, new), details={"supersedes_id": old.id, "explanation": explanation}))
    db.commit()
    db.refresh(old)
    return old
