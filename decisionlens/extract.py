"""Map-reduce decision extraction with claim-level citation grounding.

map     : split the thread into context-sized chunks, extract candidate decisions from each
ground  : every quote and reason must be found in a real post, otherwise it is dropped
reduce  : merge candidates describing the same idea across chunks, resolve the final stance
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional

from decisionlens.llm import Backend
from decisionlens.models import STATUSES, Decision, Evidence, Reason, Thread, decision_id
from decisionlens.text import chunk_posts, jaccard, normalize, overlap, sentences, token_set

GROUND_THRESHOLD = 0.6
MERGE_THRESHOLD = 0.5


def ground(claim: str, thread: Thread, preferred: int = 0) -> Optional[Evidence]:
    """Find the post sentence that supports `claim`.

    A verbatim hit wins. Otherwise the sentence with the highest token overlap is accepted if it
    clears GROUND_THRESHOLD. The cited post is tried first, then the rest of the thread.
    """
    claim = claim.strip()
    if not claim:
        return None
    norm_claim = normalize(claim)
    ordered = sorted(thread.posts, key=lambda p: 0 if p.post_id == preferred else 1)
    for p in ordered:
        if norm_claim and norm_claim in normalize(p.text):
            return Evidence(p.post_id, p.author, p.url, _surrounding(p.text, claim), verbatim=True)
    claim_tokens = token_set(claim)
    if len(claim_tokens) < 2:
        return None
    best, best_score = None, 0.0
    for p in ordered:
        for s in sentences(p.text):
            score = overlap(claim_tokens, token_set(s))
            if p.post_id == preferred:
                score += 0.05
            if score > best_score:
                best, best_score = (p, s), score
    if best and best_score >= GROUND_THRESHOLD:
        p, s = best
        return Evidence(p.post_id, p.author, p.url, s, verbatim=False)
    return None


def _surrounding(text: str, claim: str) -> str:
    for s in sentences(text):
        if normalize(claim) in normalize(s):
            return s
    return claim


def _valid_candidate(c: Dict[str, Any]) -> bool:
    return bool(c.get("idea")) and c.get("stance") in STATUSES


def extract_decisions(
    thread: Thread,
    backend: Backend,
    max_chunk_chars: int = 6000,
    keep_unverified: bool = False,
    progress=None,
) -> List[Decision]:
    candidates: List[Dict[str, Any]] = []
    chunks = chunk_posts(thread.posts, max_chars=max_chunk_chars)
    for i, chunk in enumerate(chunks, 1):
        if progress:
            progress(f"chunk {i}/{len(chunks)} ({len(chunk)} posts)")
        try:
            found = backend.extract(chunk, thread.title)
        except Exception as exc:  # one bad chunk must not sink the whole thread
            if progress:
                progress(f"chunk {i} failed: {exc}")
            continue
        candidates.extend(c for c in found if _valid_candidate(c))
    return reduce_candidates(candidates, thread, keep_unverified=keep_unverified)


def reduce_candidates(candidates: List[Dict[str, Any]], thread: Thread, keep_unverified: bool = False) -> List[Decision]:
    grounded = []
    for c in candidates:
        ev = ground(c.get("quote") or c.get("summary") or c["idea"], thread, c.get("post_id", 0))
        if ev is None and not keep_unverified:
            continue
        reasons = []
        for r in c.get("reasons", []):
            rev = ground(r, thread, c.get("post_id", 0))
            if rev is not None:
                reasons.append(Reason(r, [rev]))
            elif keep_unverified:
                reasons.append(Reason(r, []))
        grounded.append({**c, "evidence": ev, "reason_objs": reasons, "tokens": token_set(c["idea"])})

    groups: List[List[Dict[str, Any]]] = []
    for c in grounded:
        for g in groups:
            if _same_idea(c["tokens"], g[0]["tokens"]):
                g.append(c)
                break
        else:
            groups.append([c])

    decisions = []
    for g in groups:
        title = Counter(c["idea"] for c in g).most_common(1)[0][0]
        status = resolve_status(g)
        reasons: List[Reason] = []
        seen = []
        for c in g:
            for r in c["reason_objs"]:
                toks = token_set(r.text)
                if all(jaccard(toks, s) < 0.6 for s in seen):
                    reasons.append(r)
                    seen.append(toks)
        evidence: List[Evidence] = []
        for c in g:
            ev = c["evidence"]
            if ev and all((ev.post_id, ev.quote) != (e.post_id, e.quote) for e in evidence):
                evidence.append(ev)
        summary = next((c["summary"] for c in g if c.get("summary")), "")
        decisions.append(
            Decision(
                decision_id=decision_id(thread.url, title),
                title=title,
                status=status,
                summary=summary,
                reasons=reasons,
                evidence=evidence,
                source_url=thread.url,
                source_title=thread.title,
            )
        )
    return decisions


def _same_idea(a, b) -> bool:
    if not a or not b:
        return False
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    return jaccard(a, b) >= MERGE_THRESHOLD or (len(small) >= 2 and overlap(small, big) >= 0.8)


def resolve_status(group: List[Dict[str, Any]]) -> str:
    """Later posts carry more weight: discussions converge, early positions get overturned."""
    posts = sorted({c["post_id"] for c in group}) or [0]
    span = max(posts[-1] - posts[0], 1)
    score: Counter = Counter()
    for c in group:
        weight = 1.0 + (c["post_id"] - posts[0]) / span
        score[c["stance"]] += weight
    return score.most_common(1)[0][0]
