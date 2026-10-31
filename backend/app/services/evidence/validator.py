"""Independent evidence validation and decision status rules.

The extractor only proposes. This module:
1. resolves every cited source against stored GitHub data (existence, repository, original URL, quote),
2. checks that the source text supports the claim,
3. derives conflict, status and determination with fixed rules, never with vote counts or model preference.

Verification states: verified | partially_verified | unsupported | needs_human_review.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.models import Comment, Commit, Discussion, Issue, PullRequest, Repository
from app.schemas.extraction import CandidateDecision, EvidenceRef
from app.services.evidence.text import OBJECTION_CUES, RESOLUTION_CUES, normalize, overlap, sentences, tokens

VERIFIED, PARTIAL, UNSUPPORTED, REVIEW = "verified", "partially_verified", "unsupported", "needs_human_review"
AUTHORITY = {"OWNER", "MEMBER", "COLLABORATOR"}
SOURCE_ID = re.compile(r"^(comment|issue|pull_request|discussion|commit):(\d{1,18})$")
MODELS = {"comment": Comment, "issue": Issue, "pull_request": PullRequest, "discussion": Discussion, "commit": Commit}
SUPPORT_THRESHOLD = 0.5
FUZZY_QUOTE = 0.8


@dataclass
class Source:
    kind: str
    db_id: int
    repository_id: int
    text: str
    html_url: str
    author_login: Optional[str]
    author_association: Optional[str]
    review_state: Optional[str] = None
    merged: bool = False


@dataclass
class Check:
    """Result of validating one (claim, cited source) pair."""

    claim_type: str
    claim_text: str
    ref: EvidenceRef
    state: str
    flags: List[str] = field(default_factory=list)
    source: Optional[Source] = None
    quote: Optional[str] = None  # text verified to exist in the stored source
    alternative: Optional[str] = None
    stance: Optional[str] = None
    is_explicit: bool = True

    @property
    def ok(self) -> bool:
        return self.state in (VERIFIED, PARTIAL)

    @property
    def authoritative(self) -> bool:
        s = self.source
        return bool(s and (s.author_association or "").upper() in AUTHORITY)


@dataclass
class AltResult:
    name: str
    status: str
    proposed_status: str
    rejection_reason: Optional[str]
    verification_state: str


@dataclass
class Result:
    topic: str
    problem: Optional[str]
    decision: Optional[str]
    status: str
    determination: str
    conflict_detected: bool
    requires_human_review: bool
    verification_state: str
    alternatives: List[AltResult]
    checks: List[Check]
    notes: List[str]

    @property
    def can_create(self) -> bool:
        return self.verification_state != UNSUPPORTED


def _load(db: Session, kind: str, db_id: int) -> Optional[Source]:
    row = db.get(MODELS[kind], db_id)
    if row is None:
        return None
    if kind == "comment":
        return Source(kind, row.id, row.repository_id, row.body or "", row.html_url, row.author_login,
                      row.author_association, review_state=row.review_state)
    if kind in ("issue", "pull_request", "discussion"):
        text = f"{row.title}\n{row.body or ''}"
        assoc = getattr(row, "author_association", None)
        merged = kind == "pull_request" and row.gh_merged_at is not None
        return Source(kind, row.id, row.repository_id, text, row.html_url, row.author_login, assoc, merged=merged)
    return Source(kind, row.id, row.repository_id, row.message, row.html_url, row.author_login, None)


def _find_quote(quote: str, text: str) -> Tuple[Optional[str], bool]:
    """Return (verified quote, exact?)."""
    if normalize(quote) and normalize(quote) in normalize(text):
        return quote.strip(), True
    qt = tokens(quote)
    best, score = None, 0.0
    for s in sentences(text):
        sc = overlap(qt, tokens(s))
        if sc > score:
            best, score = s, sc
    return (best, False) if best and score >= FUZZY_QUOTE else (None, False)


class Validator:
    def __init__(self, db: Session, repo: Repository):
        self.db, self.repo = db, repo
        self.prefix = f"https://github.com/{repo.owner}/{repo.name}/".lower()

    def check(self, ref: EvidenceRef, claim_type: str, claim_text: str, **extra) -> Check:
        c = Check(claim_type, claim_text, ref, UNSUPPORTED, **extra)
        m = SOURCE_ID.match(ref.source_id.strip())
        if not m:
            c.flags.append("fabricated_id")  # not an ID DeciTrace ever hands out
            return c
        src = _load(self.db, m.group(1), int(m.group(2)))
        if src is None:
            c.flags.append("source_not_found")
            return c
        c.source = src
        if src.repository_id != self.repo.id:
            c.flags.append("wrong_repository")
            c.source = None  # never surface another repository's data
            return c
        if not src.html_url.lower().startswith(self.prefix):
            c.flags.append("non_github_url")
            return c
        if ref.url and ref.url.strip().rstrip("/") != src.html_url.rstrip("/"):
            c.flags.append("url_mismatch")  # the stored original URL is used instead

        basis = src.text
        if ref.quote:
            found, exact = _find_quote(ref.quote, src.text)
            if found:
                c.quote = found
                basis = found
                if not exact:
                    c.flags.append("quote_paraphrased")
            else:
                c.flags.append("quote_not_found")

        support = overlap(tokens(claim_text), tokens(basis))
        if claim_type == "resolution" and src.review_state == "APPROVED":
            support = max(support, SUPPORT_THRESHOLD)  # an approving review supports the outcome it approves
        if support == 0 and "quote_not_found" in c.flags:
            c.flags.append("does_not_support_claim")
            return c
        if support < SUPPORT_THRESHOLD:
            c.flags.append("weak_support")
        problems = {"url_mismatch", "quote_not_found", "weak_support", "quote_paraphrased"}
        c.state = PARTIAL if problems & set(c.flags) else VERIFIED
        if c.quote is None and not ref.quote:
            c.quote = _best_sentence(claim_text, src.text)
        return c


def _best_sentence(claim: str, text: str) -> Optional[str]:
    ct = tokens(claim)
    scored = sorted(((overlap(ct, tokens(s)), s) for s in sentences(text)), key=lambda x: -x[0])
    return scored[0][1] if scored and scored[0][0] > 0 else None


def _matches(name: str, text: Optional[str]) -> bool:
    nt = tokens(name)
    return bool(text) and bool(nt) and overlap(nt, tokens(text)) >= 0.6


def _aggregate(checks: List[Check]) -> str:
    if not checks or not any(c.ok for c in checks):
        return UNSUPPORTED
    return VERIFIED if all(c.state == VERIFIED for c in checks) else PARTIAL


def validate(db: Session, repo: Repository, cand: CandidateDecision) -> Result:
    v = Validator(db, repo)
    notes: List[str] = []
    checks: List[Check] = []

    resolution = [v.check(r, "resolution", cand.decision or cand.topic) for r in cand.resolution_evidence]
    checks += resolution
    alt_checks: Dict[str, List[Check]] = {}
    rej_checks: Dict[str, List[Check]] = {}
    for a in cand.alternatives:
        alt_checks[a.name] = [v.check(r, "alternative", a.name, alternative=a.name) for r in a.evidence]
        rej_text = a.rejection_reason or f"{a.name} not chosen"
        rej_checks[a.name] = [v.check(r, "rejection", rej_text, alternative=a.name) for r in a.rejection_evidence]
        checks += alt_checks[a.name] + rej_checks[a.name]
    reason_checks: List[Check] = []
    for r in cand.reasoning:
        if not r.evidence:
            reason_checks.append(Check("reason", r.reason, EvidenceRef(source_id="(none)"), UNSUPPORTED, ["no_evidence"],
                                       alternative=r.alternative, is_explicit=r.is_explicit))
        for ref in r.evidence:
            reason_checks.append(v.check(ref, "reason", r.reason, alternative=r.alternative, is_explicit=r.is_explicit))
    checks += reason_checks
    positions = [v.check(p.evidence, "position", p.alternative, alternative=p.alternative, stance=p.stance)
                 for p in cand.positions]
    checks += positions

    for c in checks:
        if c.state == UNSUPPORTED:
            notes.append(f"{c.claim_type} '{c.claim_text[:60]}' citing {c.ref.source_id}: unsupported ({', '.join(c.flags)})")

    # ---- conflict: competing proposals or opposing stances by different people (never a vote count)
    support: Dict[str, Set[str]] = {}
    oppose: Dict[str, Set[str]] = {}
    for p in positions:
        if not p.ok or not p.source:
            continue
        who = p.source.author_login or f"{p.source.kind}:{p.source.db_id}"
        (support if p.stance == "support" else oppose if p.stance == "oppose" else {}).setdefault(p.alternative, set()).add(who)
    backed = [alt for alt, people in support.items() if people]
    competing = len(backed) >= 2 and len(set().union(*(support[a] for a in backed))) >= 2
    contested = any(support.get(alt) and oppose.get(alt) for alt in set(support) | set(oppose))
    conflict = competing or contested
    if cand.conflict_detected and not conflict:
        notes.append("Extractor reported a conflict that the cited positions do not show; kept for human review.")
        conflict = True

    # ---- resolution: only an authoritative, explicit, verified statement settles a decision
    explicit = [c for c in resolution if c.state == VERIFIED and c.authoritative and c.source and (
        c.source.review_state == "APPROVED" or RESOLUTION_CUES.search(c.quote or c.source.text))]
    implied = [c for c in resolution if c.ok and c not in explicit and c.source and (
        c.source.merged or c.source.kind == "commit")]

    if cand.decision and explicit and cand.decision_status != "unresolved":
        status, determination, decision = cand.decision_status, "explicit", cand.decision
        requires_review = False
    elif cand.decision and implied and cand.decision_status == "accepted":
        status, determination, decision = "accepted", "inferred", cand.decision
        requires_review = True
        notes.append("Implemented (merged PR or commit) but no authoritative statement approves it: inferred, needs review.")
    else:
        if cand.decision:
            notes.append(f"'{cand.decision}' is not established by an authoritative, verified statement: kept unresolved.")
        status, determination, decision = "unresolved", "unresolved", None
        requires_review = conflict or bool(cand.decision) or bool(cand.alternatives)
    if conflict and determination != "explicit":
        requires_review = True

    # ---- alternatives: "rejected" needs verified objection evidence; otherwise it was only not selected
    alternatives: List[AltResult] = []
    for a in cand.alternatives:
        rej_ok = [c for c in rej_checks[a.name] if c.ok and c.source and OBJECTION_CUES.search(c.quote or c.source.text)]
        reason_support = [c for c in reason_checks if c.ok and c.alternative == a.name]
        if decision and _matches(a.name, decision):
            new = "selected"
        elif a.status == "rejected" and rej_ok and (decision or any(c.authoritative for c in rej_ok)):
            new = "rejected"
        elif a.status == "deferred" and alt_checks[a.name] and any(c.ok for c in alt_checks[a.name]) and decision:
            new = "deferred"
        else:
            new = "considered_not_selected" if decision else "proposed"
        if new != a.status:
            notes.append(f"Alternative '{a.name}': '{a.status}' changed to '{new}' by the status rules.")
        reason = a.rejection_reason if new == "rejected" and (rej_ok or reason_support) else None
        if a.rejection_reason and reason is None:
            notes.append(f"Rejection reason for '{a.name}' dropped: no verified source states it.")
        alternatives.append(AltResult(a.name, new, a.status, reason,
                                      _aggregate(alt_checks[a.name] + rej_checks[a.name])))

    if not any(c.ok for c in checks):
        state = UNSUPPORTED
    elif requires_review:
        state = REVIEW
    else:
        state = _aggregate(checks)
    return Result(cand.topic, cand.problem, decision, status, determination, conflict, requires_review, state,
                  alternatives, checks, notes)
