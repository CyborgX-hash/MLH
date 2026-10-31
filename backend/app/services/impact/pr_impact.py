"""PR impact analysis: which historical decisions a pull request touches, and where it may conflict.

Deterministic on purpose. No model judges the PR: the signals are fixed rules over the PR's changed files and
diff lines, and every finding cites the decision's own sources. A finding is a prompt for human review, never
proof that the PR is wrong, and nothing here can block or reject a PR.

Signals
- deletes_implementation   the PR deletes a file that implemented an accepted decision
- removes_decision_code    removed lines in an implementing file mention the decision's own terms, and the PR
                           does not add those terms back in that file
- introduces_rejected      added lines anywhere mention an alternative the project explicitly rejected
- touches_implementation   the PR changes a file that implemented the decision (context, not a conflict)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Decision, DecisionAlternative, DecisionCodeLink, DecisionEvidence, Repository
from app.services.evidence.text import key_terms

NOTE = ("These findings are review prompts, not proof that the pull request is wrong. DeciTrace never blocks or "
        "rejects a pull request; a person decides.")
ACCEPTED_LIKE = ("accepted",)


@dataclass
class Hit:
    signal: str
    detail: str
    file: str
    lines: List[str] = field(default_factory=list)


@dataclass
class Finding:
    decision: Decision
    severity: str  # potential_conflict | related
    hits: List[Hit] = field(default_factory=list)


def diff_lines(patch: Optional[str]) -> Tuple[List[str], List[str]]:
    added, removed = [], []
    for line in (patch or "").splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added.append(line[1:].strip())
        elif line.startswith("-"):
            removed.append(line[1:].strip())
    return added, removed


def _mentions(line: str, terms: Iterable[str]) -> Set[str]:
    low = line.lower()
    return {t for t in terms if t in low}


def analyze(db: Session, repo: Repository, files: List[dict]) -> List[Finding]:
    """`files` are GitHub PR file objects: filename, status, previous_filename, patch."""
    names: Dict[str, dict] = {}
    for f in files:
        names[f["filename"]] = f
        if f.get("previous_filename"):
            names[f["previous_filename"]] = f
    findings: Dict[int, Finding] = {}

    def finding(d: Decision, severity: str) -> Finding:
        fnd = findings.get(d.id)
        if fnd is None:
            fnd = findings[d.id] = Finding(d, severity)
        elif severity == "potential_conflict":
            fnd.severity = severity
        return fnd

    # 1. Decisions whose implementation touched one of the changed files (by old or current name).
    links = db.execute(
        select(DecisionCodeLink, Decision).join(Decision, DecisionCodeLink.decision_id == Decision.id).where(
            Decision.repository_id == repo.id, Decision.status != "superseded",
            or_(DecisionCodeLink.path.in_(list(names)), DecisionCodeLink.current_path.in_(list(names))))
    ).all()
    for link, d in links:
        f = names.get(link.current_path or "") or names.get(link.path or "")
        if f is None:
            continue
        alts = db.scalars(select(DecisionAlternative).where(DecisionAlternative.decision_id == d.id)).all()
        selected = [a.name for a in alts if a.status == "selected"]
        reasons = db.scalars(select(DecisionEvidence.claim_text).where(
            DecisionEvidence.decision_id == d.id, DecisionEvidence.claim_type == "reason",
            DecisionEvidence.verification_state != "unsupported")).all()
        terms = key_terms(d.decision, *selected, *reasons)
        pr_ref = f"PR #{link.pr_number}" if link.pr_number else "the implementing change"
        possible = " (possible mapping)" if link.link_status == "possible" else ""
        settled = d.status in ACCEPTED_LIKE

        if f["status"] == "removed" and settled:
            finding(d, "potential_conflict").hits.append(Hit(
                "deletes_implementation",
                f"Deletes {f['filename']}, which implemented this decision in {pr_ref}{possible}.", f["filename"]))
            continue
        added, removed = diff_lines(f.get("patch"))
        readded = set().union(*(_mentions(a, terms) for a in added)) if added else set()
        dropped = [(r, _mentions(r, terms) - readded) for r in removed]
        dropped = [(r, t) for r, t in dropped if t]
        if dropped and settled:
            gone = sorted(set().union(*(t for _, t in dropped)))
            finding(d, "potential_conflict").hits.append(Hit(
                "removes_decision_code",
                f"Removes lines mentioning {', '.join(gone)} from {f['filename']} and does not add them back; "
                f"this file implemented the decision in {pr_ref}{possible}.", f["filename"], [r for r, _ in dropped][:5]))
        else:
            finding(d, "related").hits.append(Hit(
                "touches_implementation",
                f"Changes {f['filename']}, which implemented this decision in {pr_ref}{possible}.", f["filename"]))

    # 2. Rejected alternatives reappearing anywhere in the PR (only rejections the validator or a reviewer kept).
    rejected = db.execute(
        select(DecisionAlternative, Decision).join(Decision, DecisionAlternative.decision_id == Decision.id).where(
            Decision.repository_id == repo.id, Decision.status != "superseded",
            DecisionAlternative.status == "rejected")
    ).all()
    for alt, d in rejected:
        terms = key_terms(alt.name)
        if not terms:
            continue
        for f in files:
            added, _ = diff_lines(f.get("patch"))
            lines = [a for a in added if terms <= _mentions(a, terms)]  # every distinctive term on one line
            if lines:
                why = f" (recorded reason: {alt.rejection_reason})" if alt.rejection_reason else " (reason not recorded)"
                finding(d, "potential_conflict").hits.append(Hit(
                    "introduces_rejected",
                    f"Adds code mentioning {alt.name}, an alternative this project rejected{why}.", f["filename"], lines[:5]))
    order = {"potential_conflict": 0, "related": 1}
    return sorted(findings.values(), key=lambda x: (order[x.severity], x.decision.id))


def supporting_sources(db: Session, d: Decision, limit: int = 4) -> List[dict]:
    rows = db.scalars(select(DecisionEvidence).where(
        DecisionEvidence.decision_id == d.id, DecisionEvidence.html_url.is_not(None),
        DecisionEvidence.verification_state != "unsupported",
        DecisionEvidence.claim_type.in_(("resolution", "reason", "rejection")))
        .order_by(DecisionEvidence.verification_state.desc(), DecisionEvidence.id)).all()
    seen, out = set(), []
    for e in rows:
        if e.html_url in seen:
            continue
        seen.add(e.html_url)
        out.append({"url": e.html_url, "author": e.author_login, "claim_type": e.claim_type,
                    "quote": e.quote or e.claim_text, "verification_state": e.verification_state})
        if len(out) >= limit:
            break
    return out
