"""Hybrid retrieval: SQL metadata filters + PostgreSQL full-text search + pgvector similarity,
fused with reciprocal rank fusion, then expanded with each decision's verified evidence and implementation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from sqlalchemy import Text, cast, func, select, text
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.orm import Session

from app.models import Comment, Decision, DecisionAlternative, DecisionEvidence, KnowledgeChunk
from app.services.ai.client import AIClient, AIError
from app.services.impact.code_map import map_decision

RRF_K = 60
MAX_VECTOR_DISTANCE = 0.55  # cosine distance; farther is treated as unrelated
CANDIDATES = 40


@dataclass
class Hit:
    chunk: KnowledgeChunk
    score: float
    lexical: bool = False
    semantic: bool = False


@dataclass
class Retrieval:
    hits: List[Hit]
    mode: str  # hybrid | full_text
    note: Optional[str] = None


def _or_query(question: str):
    # plainto_tsquery ANDs every word; questions need OR semantics, ranked by ts_rank_cd.
    anded = cast(func.plainto_tsquery("english", question), Text)
    return cast(func.replace(anded, "&", "|"), TSQUERY)


def hybrid_search(
    db: Session, repo_id: int, question: str, ai: Optional[AIClient], kinds: Optional[Sequence[str]] = None,
    decision_statuses: Optional[Sequence[str]] = None, k: int = 12,
) -> Retrieval:
    base = select(KnowledgeChunk).where(KnowledgeChunk.repository_id == repo_id)
    if kinds:
        base = base.where(KnowledgeChunk.kind.in_(kinds))
    if decision_statuses:
        base = base.where((KnowledgeChunk.kind != "decision") | KnowledgeChunk.decision_status.in_(decision_statuses))

    ranks: Dict[int, Hit] = {}
    q = _or_query(question)
    lexical = db.execute(
        base.add_columns(func.ts_rank_cd(KnowledgeChunk.tsv, q).label("r"))
        .where(KnowledgeChunk.tsv.op("@@")(q)).order_by(text("r DESC")).limit(CANDIDATES)
    ).all()
    for rank, (chunk, _) in enumerate(lexical):
        ranks[chunk.id] = Hit(chunk, 1 / (RRF_K + rank), lexical=True)

    mode, note = "full_text", None
    if ai is not None and ai.embed_model:
        try:
            [qv] = ai.embed([question])
            dist = KnowledgeChunk.embedding.cosine_distance(qv)
            semantic = db.execute(
                base.add_columns(dist.label("d")).where(
                    KnowledgeChunk.embedding.is_not(None), KnowledgeChunk.embed_model == ai.embed_model)
                .order_by(dist).limit(CANDIDATES)
            ).all()
            for rank, (chunk, d) in enumerate(semantic):
                if d > MAX_VECTOR_DISTANCE:
                    break
                hit = ranks.setdefault(chunk.id, Hit(chunk, 0.0))
                hit.score += 1 / (RRF_K + rank)
                hit.semantic = True
            mode = "hybrid"
        except AIError as exc:
            note = f"Vector search unavailable ({exc}); used full-text search only."
    else:
        note = "No embedding model configured; used full-text search only."

    for hit in ranks.values():
        if hit.chunk.kind == "decision":
            hit.score *= 1.5  # validated decisions outrank raw discussion
    best: Dict[tuple, Hit] = {}
    for hit in sorted(ranks.values(), key=lambda h: -h.score):
        best.setdefault((hit.chunk.kind, hit.chunk.ref_id), hit)  # one chunk per record
    return Retrieval(sorted(best.values(), key=lambda h: -h.score)[:k], mode, note)


@dataclass
class ContextItem:
    sid: str
    source_type: str  # decision | issue | pull_request | discussion | commit | file | comment
    number: Optional[int]
    url: Optional[str]
    title: str
    text: str
    author: Optional[str] = None
    decision_id: Optional[int] = None
    verified: bool = False  # the item is verified decision evidence


@dataclass
class Context:
    items: List[ContextItem] = field(default_factory=list)
    decisions: List[dict] = field(default_factory=list)

    def add(self, **kw) -> ContextItem:
        for it in self.items:
            if kw.get("url") and it.url == kw["url"]:
                return it
        item = ContextItem(sid=f"S{len(self.items) + 1}", **kw)
        self.items.append(item)
        return item


def build_context(db: Session, retrieval: Retrieval, max_chars: int = 12000) -> Context:
    ctx = Context()
    used = 0
    for hit in retrieval.hits:
        c = hit.chunk
        if used > max_chars:
            break
        if c.kind == "decision":
            d = db.get(Decision, c.ref_id)
            if d is None:
                continue
            code = map_decision(db, d)
            impl = ("No verified implementation evidence found." if code["message"] else
                    "Implemented in " + ", ".join(sorted({f"PR #{r.pr_number}" if r.pr_number else f"commit {r.commit_sha[:7]}"
                                                          for r in code["verified"]})) + ".")
            ctx.add(source_type="decision", number=d.id, url=None, title=c.title, text=f"{c.text}\nImplementation: {impl}",
                    decision_id=d.id, verified=d.determination in ("explicit", "human_confirmed"))
            used += len(c.text)
            alts = db.scalars(select(DecisionAlternative).where(DecisionAlternative.decision_id == d.id)).all()
            ctx.decisions.append({
                "id": d.id, "topic": d.topic, "status": d.status, "determination": d.determination,
                "decision": d.decision, "conflict_detected": d.conflict_detected,
                "requires_human_review": d.requires_human_review,
                "implementation": "verified" if not code["message"] else "none",
                "alternatives": [{"name": a.name, "status": a.status, "rejection_reason": a.rejection_reason} for a in alts],
            })
            evidence = db.scalars(select(DecisionEvidence).where(
                DecisionEvidence.decision_id == d.id, DecisionEvidence.html_url.is_not(None),
                DecisionEvidence.verification_state.in_(("verified", "partially_verified")))
                .order_by(DecisionEvidence.verification_state.desc(), DecisionEvidence.id)).all()
            for e in evidence[:6]:
                what = f"{e.claim_type}" + (f" ({e.stance} {e.alternative})" if e.stance else "")
                stype, number = e.source_kind, None
                if e.source_kind == "comment":  # cite a comment as its discussion / issue / PR and number
                    cm = db.get(Comment, e.source_db_id)
                    stype, number = (cm.parent_kind, cm.parent_number) if cm else ("comment", None)
                ctx.add(source_type=stype or "comment", number=number, url=e.html_url,
                        title=f"Evidence for decision {d.id}: {what} by @{e.author_login}",
                        text=e.quote or e.claim_text, author=e.author_login, decision_id=d.id,
                        verified=e.verification_state == "verified")
                used += len(e.quote or e.claim_text)
        else:
            stype = c.parent_kind if c.kind == "comment" else c.kind
            ctx.add(source_type=stype, number=c.number, url=c.url, title=c.title, text=c.text[:1500], author=c.author_login)
            used += min(len(c.text), 1500)
    return ctx
