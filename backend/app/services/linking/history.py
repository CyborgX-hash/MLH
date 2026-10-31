"""Decision history across sources, and detection of duplicate decisions from related discussions."""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Comment, Commit, Decision, DecisionEvidence, Discussion, Issue, PullRequest, SourceLink
from app.services.evidence.text import overlap, tokens

Key = Tuple[str, int]
RECORD_MODELS = {"issue": Issue, "pull_request": PullRequest, "discussion": Discussion, "commit": Commit}
DUPLICATE_TOPIC_OVERLAP = 0.5


def record_of(db: Session, kind: Optional[str], db_id: Optional[int]) -> Optional[Key]:
    """The top-level record a source belongs to (a comment belongs to its issue, PR or discussion)."""
    if not kind or db_id is None:
        return None
    if kind in RECORD_MODELS:
        return (kind, db_id)
    c = db.get(Comment, db_id)
    if c is None:
        return None
    model = RECORD_MODELS[c.parent_kind]
    rid = db.scalar(select(model.id).where(model.repository_id == c.repository_id, model.number == c.parent_number))
    return (c.parent_kind, rid) if rid else None


def records_for_sources(db: Session, sources: Iterable[Tuple[Optional[str], Optional[int]]]) -> Set[Key]:
    out = set()
    for kind, db_id in sources:
        key = record_of(db, kind, db_id)
        if key:
            out.add(key)
    return out


def decision_records(db: Session, decision_id: int) -> Set[Key]:
    rows = db.execute(
        select(DecisionEvidence.source_kind, DecisionEvidence.source_db_id).where(
            DecisionEvidence.decision_id == decision_id, DecisionEvidence.verification_state != "unsupported"
        )
    )
    return records_for_sources(db, rows)


def links_touching(db: Session, repo_id: int, keys: Set[Key], verified_only: bool = False) -> List[SourceLink]:
    if not keys:
        return []
    conds = []
    for kind, rid in keys:
        conds.append((SourceLink.source_kind == kind) & (SourceLink.source_id == rid))
        conds.append((SourceLink.target_kind == kind) & (SourceLink.target_id == rid))
    q = select(SourceLink).where(SourceLink.repository_id == repo_id, or_(*conds))
    if verified_only:
        q = q.where(SourceLink.verification_status == "verified")
    return list(db.scalars(q))


def expand(db: Session, repo_id: int, keys: Set[Key]) -> Set[Key]:
    """The records plus everything one *verified* link away."""
    out = set(keys)
    for link in links_touching(db, repo_id, keys, verified_only=True):
        out.add((link.source_kind, link.source_id))
        out.add((link.target_kind, link.target_id))
    return out


def describe(db: Session, key: Key) -> Dict:
    kind, rid = key
    rec = db.get(RECORD_MODELS[kind], rid)
    if rec is None:
        return {"kind": kind, "id": rid, "missing": True}
    if kind == "commit":
        return {"kind": kind, "id": rid, "number": None, "title": rec.message.split("\n", 1)[0][:200],
                "url": rec.html_url, "sha": rec.sha}
    return {"kind": kind, "id": rid, "number": rec.number, "title": rec.title, "url": rec.html_url,
            "state": getattr(rec, "state", None)}


def related_graph(db: Session, decision: Decision) -> Dict:
    """Records cited by the decision, plus records linked to them (verified and possible, labelled)."""
    cited = decision_records(db, decision.id)
    links = links_touching(db, decision.repository_id, cited)
    keys = set(cited)
    for link in links:
        keys.add((link.source_kind, link.source_id))
        keys.add((link.target_kind, link.target_id))
    return {
        "records": [dict(describe(db, k), cited=k in cited) for k in sorted(keys)],
        "links": [
            {"source": {"kind": l.source_kind, "id": l.source_id}, "target": {"kind": l.target_kind, "id": l.target_id},
             "relation": l.relation, "signal": l.signal, "verification_status": l.verification_status,
             "confidence": l.confidence, "evidence": l.evidence}
            for l in sorted(links, key=lambda l: (l.verification_status != "verified", -l.confidence))
        ],
    }


def find_duplicate(db: Session, repo_id: int, topic: str, decision_text: Optional[str], cited: Set[Key]) -> Optional[Decision]:
    """An existing live decision about the same topic whose sources are explicitly linked to these ones."""
    if not cited:
        return None
    neighbourhood = expand(db, repo_id, cited)
    wanted = tokens(f"{topic} {decision_text or ''}")
    for d in db.scalars(select(Decision).where(Decision.repository_id == repo_id, Decision.status != "superseded")):
        theirs = decision_records(db, d.id)
        if not theirs & neighbourhood:
            continue
        other = tokens(f"{d.topic} {d.decision or ''}")
        small, big = (wanted, other) if len(wanted) <= len(other) else (other, wanted)
        if overlap(small, big) >= DUPLICATE_TOPIC_OVERLAP:
            return d
    return None
