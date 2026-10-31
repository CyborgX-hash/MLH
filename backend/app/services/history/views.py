"""Dashboard overview, decision timeline and decision graph.

Everything here is derived from stored rows. The timeline and graph never add a relationship the backend has
not established: evidence rows, source links, code links, reviews and supersede pointers are the only inputs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Comment, Commit, Decision, DecisionAlternative, DecisionCodeLink, DecisionEvent, DecisionEvidence, DecisionReview,
    Discussion, Issue, PullRequest, Repository, SourceFile,
)
from app.services.impact.code_map import map_decision
from app.services.linking.history import RECORD_MODELS, describe, record_of, related_graph

ALT_EDGE = {"selected": "accepted", "rejected": "rejected", "considered_not_selected": "considered",
            "proposed": "proposed", "deferred": "deferred"}


def overview(db: Session, repo: Repository) -> Dict:
    rid = repo.id

    def count(model, *where):
        return db.scalar(select(func.count()).select_from(model).where(model.repository_id == rid, *where)) or 0

    by_status = dict(db.execute(select(Decision.status, func.count()).where(Decision.repository_id == rid)
                                .group_by(Decision.status)).all())
    rejected_alts = db.scalar(
        select(func.count()).select_from(DecisionAlternative).join(Decision, DecisionAlternative.decision_id == Decision.id)
        .where(Decision.repository_id == rid, DecisionAlternative.status == "rejected")) or 0
    recent = db.execute(
        select(DecisionEvent, Decision.topic).join(Decision, DecisionEvent.decision_id == Decision.id)
        .where(Decision.repository_id == rid).order_by(DecisionEvent.created_at.desc(), DecisionEvent.id.desc()).limit(10)
    ).all()
    issues, prs, discussions = count(Issue), count(PullRequest), count(Discussion)
    return {
        "counts": {
            "issues": issues, "pull_requests": prs, "discussions": discussions,
            "discussions_collected": issues + prs + discussions, "comments": count(Comment), "commits": count(Commit),
            "source_files": count(SourceFile), "decisions": sum(by_status.values()),
            "accepted": by_status.get("accepted", 0), "rejected": by_status.get("rejected", 0),
            "unresolved": by_status.get("unresolved", 0), "deferred": by_status.get("deferred", 0),
            "superseded": by_status.get("superseded", 0),
            "needs_review": count(Decision, Decision.requires_human_review.is_(True)),
            "rejected_alternatives": rejected_alts,
        },
        "recent_activity": [
            {"decision_id": e.decision_id, "topic": topic, "event": e.event, "actor": e.actor, "at": e.created_at}
            for e, topic in recent
        ],
    }


def _source_time(db: Session, kind: Optional[str], db_id: Optional[int]) -> Optional[datetime]:
    if not kind or db_id is None:
        return None
    if kind == "comment":
        c = db.get(Comment, db_id)
        return c.gh_created_at if c else None
    if kind == "commit":
        c = db.get(Commit, db_id)
        return c.authored_at or c.committed_at if c else None
    rec = db.get(RECORD_MODELS[kind], db_id)
    return rec.gh_created_at if rec else None


def timeline(db: Session, d: Decision) -> List[Dict]:
    map_decision(db, d)  # implementation links reflect the latest sync
    events: List[Dict] = []
    seen = set()

    def add(kind: str, label: str, at, url: Optional[str], author=None, quote=None, verified=True, source="github"):
        key = (kind, url, label)
        if key in seen:
            return
        seen.add(key)
        events.append({"type": kind, "label": label, "at": at, "url": url, "author": author, "quote": quote,
                       "verified": verified, "source": source})

    rows = db.scalars(select(DecisionEvidence).where(
        DecisionEvidence.decision_id == d.id, DecisionEvidence.html_url.is_not(None),
        DecisionEvidence.verification_state != "unsupported").order_by(DecisionEvidence.id)).all()
    for e in rows:
        at = _source_time(db, e.source_kind, e.source_db_id)
        verified = e.verification_state == "verified"
        if e.claim_type == "alternative" or (e.claim_type == "position" and e.stance == "support"):
            add("proposal", f"{e.alternative} proposed or supported", at, e.html_url, e.author_login, e.quote, verified)
        elif e.claim_type == "position" and e.stance == "oppose":
            add("argument", f"Argument against {e.alternative}", at, e.html_url, e.author_login, e.quote, verified)
        elif e.claim_type == "position":
            add("argument", f"Comment on {e.alternative}", at, e.html_url, e.author_login, e.quote, verified)
        elif e.claim_type == "reason":
            add("argument", f"Reasoning: {e.claim_text}", at, e.html_url, e.author_login, e.quote, verified)
        elif e.claim_type == "rejection":
            add("rejection", f"Objection to {e.alternative}", at, e.html_url, e.author_login, e.quote, verified)
        elif e.claim_type == "resolution":
            if d.determination == "explicit" and verified and d.decision:
                add("approval", f"Approved: {d.decision}", at, e.html_url, e.author_login, e.quote, True)
            else:  # never call something an approval unless the validator established it
                add("argument", "Statement cited as a resolution (not an established approval)", at, e.html_url,
                    e.author_login, e.quote, False)

    for link in db.scalars(select(DecisionCodeLink).where(DecisionCodeLink.decision_id == d.id,
                                                          DecisionCodeLink.link_status == "verified")):
        if link.pr_number:
            add("implementation", f"Implemented in PR #{link.pr_number}", link.merged_at, link.pr_url)
        if link.commit_sha and link.commit_url:
            add("commit", f"Commit {link.commit_sha[:7]}", link.merged_at, link.commit_url)

    for r in db.scalars(select(DecisionReview).where(DecisionReview.decision_id == d.id)):
        label = (f"Superseded (recorded by @{r.reviewer_login})" if r.action == "supersede"
                 else f"Human review by @{r.reviewer_login}: {r.outcome_status}"
                 + (f" ({r.selected_alternative})" if r.selected_alternative else ""))
        add("human_review" if r.action != "supersede" else "superseded", label, r.created_at, None, r.reviewer_login,
            r.explanation, True, source="decitrace_review")
    if d.superseded_by_id:
        newer = db.get(Decision, d.superseded_by_id)
        at = db.scalar(select(DecisionEvent.created_at).where(DecisionEvent.decision_id == d.id,
                                                              DecisionEvent.event == "superseded"))
        add("superseded", f"Superseded by decision: {newer.topic if newer else d.superseded_by_id}", at,
            f"decision:{d.superseded_by_id}", source="decitrace_decision")

    far = datetime.max.replace(tzinfo=None)
    return sorted(events, key=lambda ev: (ev["at"].replace(tzinfo=None) if ev["at"] else far))


def graph(db: Session, d: Decision) -> Dict:
    map_decision(db, d)
    nodes: Dict[str, Dict] = {}
    edges: Dict[Tuple[str, str, str], Dict] = {}

    def node(nid: str, kind: str, label: str, url: Optional[str] = None, **extra) -> str:
        nodes.setdefault(nid, {"id": nid, "kind": kind, "label": label, "url": url, **extra})
        return nid

    def edge(a: str, b: str, label: str, status: str = "verified") -> None:
        key = (a, b, label)
        if key not in edges or edges[key]["status"] == "possible":
            edges[key] = {"source": a, "target": b, "label": label, "status": status}

    def record_node(key) -> str:
        info = describe(db, key)
        if info.get("missing"):
            return node(f"{key[0]}:{key[1]}", key[0], key[0])
        label = f"Commit {info['sha'][:7]}" if key[0] == "commit" else \
            f"{ {'issue': 'Issue', 'pull_request': 'PR', 'discussion': 'Discussion'}[key[0]]} #{info['number']}"
        return node(f"{key[0]}:{key[1]}", key[0], label, info.get("url"), title=info.get("title"))

    dn = node(f"decision:{d.id}", "decision", d.topic, None, status=d.status, determination=d.determination)
    alts = db.scalars(select(DecisionAlternative).where(DecisionAlternative.decision_id == d.id)).all()
    for a in alts:
        an = node(f"alternative:{d.id}:{a.name}", "alternative", a.name, None, status=a.status)
        edge(dn, an, ALT_EDGE.get(a.status, a.status))

    for e in db.scalars(select(DecisionEvidence).where(
            DecisionEvidence.decision_id == d.id, DecisionEvidence.verification_state != "unsupported",
            DecisionEvidence.source_kind.is_not(None))):
        key = record_of(db, e.source_kind, e.source_db_id)
        if key is None:
            continue
        rn = record_node(key)
        edge(rn, dn, "evidence")
        if e.author_login:
            un = node(f"user:{e.author_login}", "contributor", f"@{e.author_login}", f"https://github.com/{e.author_login}")
            edge(un, rn, "commented on")
            alt_id = f"alternative:{d.id}:{e.alternative}"
            if e.alternative and alt_id in nodes:
                if e.claim_type == "alternative" or (e.claim_type == "position" and e.stance == "support"):
                    edge(un, alt_id, "proposed")
                elif e.claim_type == "rejection" or e.stance == "oppose":
                    edge(un, alt_id, "argued against")

    rel = related_graph(db, d)
    for link in rel["links"]:
        a = record_node((link["source"]["kind"], link["source"]["id"]))
        b = record_node((link["target"]["kind"], link["target"]["id"]))
        edge(a, b, link["relation"], link["verification_status"])

    for c in db.scalars(select(DecisionCodeLink).where(DecisionCodeLink.decision_id == d.id)):
        if c.pull_request_id:
            pn = record_node(("pull_request", c.pull_request_id))
            edge(pn, dn, "implemented", c.link_status)
            if c.path:
                shown = c.current_path or c.path
                fn = node(f"file:{shown}", "file", shown, None, deleted=c.deleted, original_path=c.path)
                edge(pn, fn, "changed", c.link_status)
        elif c.commit_sha:
            cid = db.scalar(select(Commit.id).where(Commit.repository_id == d.repository_id, Commit.sha == c.commit_sha))
            if cid:
                edge(record_node(("commit", cid)), dn, "implemented", c.link_status)

    if d.superseded_by_id:
        newer = db.get(Decision, d.superseded_by_id)
        if newer:
            nn = node(f"decision:{newer.id}", "decision", newer.topic, None, status=newer.status)
            edge(nn, dn, "supersedes")
    for older in db.scalars(select(Decision).where(Decision.superseded_by_id == d.id)):
        on = node(f"decision:{older.id}", "decision", older.topic, None, status=older.status)
        edge(dn, on, "supersedes")
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}
