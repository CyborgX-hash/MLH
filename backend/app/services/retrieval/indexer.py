"""Build the repository knowledge base: chunks for decisions, discussion records, commits and key files.

Runs after ingestion (and refreshes decisions before answering). Unchanged chunks keep their embeddings;
changed chunks are re-embedded. Without an embedding model the index still serves full-text search.
"""
from __future__ import annotations

import hashlib
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import and_, case, delete, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    Comment, Commit, Decision, DecisionAlternative, DecisionEvidence, Discussion, Issue, KnowledgeChunk, PullRequest,
    Repository, SourceFile,
)
from app.services.ai.client import AIClient, AIError

MAX_CHUNK = 1500
MIN_COMMENT = 20
RECORD_KINDS = ("issue", "pull_request", "discussion", "comment", "commit", "file")


def _chunks(text: str, size: int = MAX_CHUNK) -> List[str]:
    text = (text or "").strip()
    if len(text) <= size:
        return [text]
    out, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        cut = text.rfind("\n", start + size // 2, end) if end < len(text) else end
        end = cut if cut > start else end
        out.append(text[start:end].strip())
        start = end
    return [c for c in out if c]


def decision_text(db: Session, d: Decision) -> str:
    """A plain-language summary that keeps status semantics explicit for retrieval and answering."""
    alts = db.scalars(select(DecisionAlternative).where(DecisionAlternative.decision_id == d.id)).all()
    reasons = db.scalars(select(DecisionEvidence.claim_text).where(
        DecisionEvidence.decision_id == d.id, DecisionEvidence.claim_type == "reason",
        DecisionEvidence.verification_state.in_(("verified", "partially_verified")))).all()
    how = {"explicit": "explicitly stated in the sources", "inferred": "inferred, not explicitly approved",
           "human_confirmed": "confirmed by an authorised human reviewer",
           "unresolved": "no authoritative resolution"}.get(d.determination, d.determination)
    lines = [f"Decision topic: {d.topic}", f"Status: {d.status} ({how})."]
    if d.problem:
        lines.append(f"Problem: {d.problem}")
    lines.append(f"Outcome: {d.decision}" if d.decision else "Outcome: none established.")
    if d.conflict_detected:
        lines.append("Participants disagreed (conflict detected).")
    for a in alts:
        s = f"Alternative {a.name}: {a.status.replace('_', ' ')}"
        if a.status == "rejected":
            s += f"; reason: {a.rejection_reason}" if a.rejection_reason else "; rejection reason not recorded in the sources"
        lines.append(s + ".")
    lines += [f"Reason: {r}" for r in dict.fromkeys(reasons)]
    if d.superseded_by_id:
        lines.append(f"Superseded by decision {d.superseded_by_id}.")
    return "\n".join(lines)


def _record_rows(db: Session, repo: Repository) -> Iterable[dict]:
    rid = repo.id
    for i in db.scalars(select(Issue).where(Issue.repository_id == rid)):
        yield dict(kind="issue", ref_id=i.id, number=i.number, title=f"Issue #{i.number}: {i.title}", url=i.html_url,
                   author_login=i.author_login, text=i.body or "")
    for p in db.scalars(select(PullRequest).where(PullRequest.repository_id == rid)):
        state = "merged" if p.gh_merged_at else p.state
        yield dict(kind="pull_request", ref_id=p.id, number=p.number, title=f"PR #{p.number} ({state}): {p.title}",
                   url=p.html_url, author_login=p.author_login, text=p.body or "")
    for d in db.scalars(select(Discussion).where(Discussion.repository_id == rid)):
        yield dict(kind="discussion", ref_id=d.id, number=d.number, title=f"Discussion #{d.number}: {d.title}",
                   url=d.html_url, author_login=d.author_login, text=d.body or "")
    for c in db.scalars(select(Comment).where(Comment.repository_id == rid)):
        if len(c.body or "") < MIN_COMMENT:
            continue
        label = {"issue": "issue", "pull_request": "PR", "discussion": "discussion"}[c.parent_kind]
        what = "review" if c.kind == "review" else "comment"
        yield dict(kind="comment", ref_id=c.id, parent_kind=c.parent_kind, number=c.parent_number,
                   title=f"{what} by @{c.author_login} on {label} #{c.parent_number}", url=c.html_url,
                   author_login=c.author_login, text=c.body)
    for c in db.scalars(select(Commit).where(Commit.repository_id == rid)):
        yield dict(kind="commit", ref_id=c.id, title=f"Commit {c.sha[:7]}", url=c.html_url,
                   author_login=c.author_login, text=c.message)
    for f in db.scalars(select(SourceFile).where(SourceFile.repository_id == rid, SourceFile.priority <= 2,
                                                 SourceFile.content.is_not(None))):
        yield dict(kind="file", ref_id=f.id, title=f"File {f.path}", url=f.html_url, text=f.content)


def _decision_rows(db: Session, repo: Repository) -> Iterable[dict]:
    for d in db.scalars(select(Decision).where(Decision.repository_id == repo.id)):
        yield dict(kind="decision", ref_id=d.id, title=f"Decision: {d.topic}", url=f"decision:{d.id}",
                   decision_status=d.status, text=decision_text(db, d))


def _write(db: Session, repo: Repository, rows: Iterable[dict], kinds: Sequence[str]) -> int:
    keep: Set[Tuple[str, int, int]] = set()
    values = []
    for row in rows:
        for n, piece in enumerate(_chunks(row["text"]) or [""]):
            text = piece or row["title"]
            values.append({
                "repository_id": repo.id, "kind": row["kind"], "ref_id": row["ref_id"], "chunk_no": n,
                "parent_kind": row.get("parent_kind"), "number": row.get("number"), "title": row["title"],
                "url": row["url"], "author_login": row.get("author_login"), "decision_status": row.get("decision_status"),
                "text": text, "content_hash": hashlib.sha1(f"{row['title']}\n{text}".encode()).hexdigest(),
            })
            keep.add((row["kind"], row["ref_id"], n))
    for i in range(0, len(values), 500):
        stmt = insert(KnowledgeChunk).values(values[i : i + 500])
        ex = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["repository_id", "kind", "ref_id", "chunk_no"],
            set_={
                **{c: ex[c] for c in ("parent_kind", "number", "title", "url", "author_login", "decision_status", "text")},
                "content_hash": ex.content_hash,
                # changed text invalidates the embedding; unchanged text keeps it
                "embedding": case((KnowledgeChunk.content_hash == ex.content_hash, KnowledgeChunk.embedding), else_=None),
                "embed_model": case((KnowledgeChunk.content_hash == ex.content_hash, KnowledgeChunk.embed_model), else_=None),
            },
        )
        db.execute(stmt)
    existing = db.execute(select(KnowledgeChunk.id, KnowledgeChunk.kind, KnowledgeChunk.ref_id, KnowledgeChunk.chunk_no)
                          .where(KnowledgeChunk.repository_id == repo.id, KnowledgeChunk.kind.in_(kinds)))
    stale = [cid for cid, k, r, n in existing if (k, r, n) not in keep]
    if stale:
        db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.id.in_(stale)))
    return len(values)


def embed_missing(db: Session, repo: Repository, ai: Optional[AIClient], batch: int = 32) -> Dict[str, object]:
    if ai is None or not ai.embed_model:
        return {"embedded": 0, "vector_search": False, "reason": "No embedding model configured."}
    q = select(KnowledgeChunk).where(KnowledgeChunk.repository_id == repo.id, or_(
        KnowledgeChunk.embedding.is_(None), KnowledgeChunk.embed_model != ai.embed_model))
    pending = list(db.scalars(q))
    done = 0
    for i in range(0, len(pending), batch):
        part = pending[i : i + batch]
        try:
            vectors = ai.embed([f"{c.title}\n{c.text}"[:4000] for c in part])
        except AIError as exc:
            db.commit()
            return {"embedded": done, "vector_search": done > 0, "reason": str(exc)}
        for c, v in zip(part, vectors):
            c.embedding, c.embed_model = v, ai.embed_model
        done += len(part)
        db.commit()
    return {"embedded": done, "vector_search": True}


def index_decisions(db: Session, repo: Repository, ai: Optional[AIClient] = None) -> int:
    n = _write(db, repo, _decision_rows(db, repo), ["decision"])
    db.commit()
    embed_missing(db, repo, ai)
    return n


def build_index(db: Session, repo: Repository, ai: Optional[AIClient] = None) -> Dict[str, object]:
    chunks = _write(db, repo, _record_rows(db, repo), RECORD_KINDS)
    chunks += _write(db, repo, _decision_rows(db, repo), ["decision"])
    db.commit()
    return {"chunks": chunks, **embed_missing(db, repo, ai)}
