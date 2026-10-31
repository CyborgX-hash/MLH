"""PR intelligence: surface historical decisions relevant to a change.

Output is printed locally. This tool never posts comments to any real project.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Set, Tuple

from decisionlens.codelink import RenameMap, _git
from decisionlens.models import Decision
from decisionlens.retrieval import DecisionIndex

DIFF_FILE = re.compile(r"^diff --git a/(\S+) b/(\S+)", re.M)
DIFF_SYMBOL = re.compile(r"^[+-]\s*(?:async\s+def|def|class|fn|func|function)\s+(\w+)", re.M)
HUNK_SYMBOL = re.compile(r"^@@[^@]*@@\s*(?:async\s+def|def|class|fn|func|function)?\s*(\w+)", re.M)


@dataclass
class Match:
    decision: Decision
    score: float
    reasons: List[str] = field(default_factory=list)


def parse_diff(diff: str) -> Tuple[Set[str], Set[str]]:
    files = {m.group(2) for m in DIFF_FILE.finditer(diff)}
    symbols = {m.group(1) for m in DIFF_SYMBOL.finditer(diff)} | {m.group(1) for m in HUNK_SYMBOL.finditer(diff)}
    return files, symbols


def git_changed_files(repo: str, base: str, head: str) -> Set[str]:
    return set(_git(repo, "diff", "--name-only", "-M", f"{base}...{head}").splitlines())


def surface(
    decisions: List[Decision],
    changed_files: Sequence[str],
    changed_symbols: Sequence[str] = (),
    pr_text: str = "",
    repo: Optional[str] = None,
    k: int = 5,
    prefer: str = "auto",
) -> List[Match]:
    rename = RenameMap.build(repo) if repo else RenameMap()
    files = set(changed_files)
    symbols = set(changed_symbols)
    scores = {d.decision_id: Match(d, 0.0) for d in decisions}

    for d in decisions:
        m = scores[d.decision_id]
        for ref in d.code_refs:
            current = rename.current(ref.path)
            if current and current in files:
                m.score += 3.0
                moved = f" (recorded as {ref.path})" if current != ref.path else ""
                m.reasons.append(f"touches linked file {current}{moved}")
            if ref.symbol and ref.symbol.split(".")[-1] in symbols:
                m.score += 2.0
                m.reasons.append(f"changes linked symbol {ref.symbol}")

    query = " ".join([pr_text] + sorted(symbols))
    if query.strip() and decisions:
        index = DecisionIndex(decisions, prefer=prefer)
        for sim, d in index.search(query, k=len(decisions)):
            if sim > 0.1:
                scores[d.decision_id].score += 2.0 * sim
                scores[d.decision_id].reasons.append(f"semantically similar to PR text ({sim:.2f})")

    ranked = sorted((m for m in scores.values() if m.score > 0), key=lambda m: -m.score)
    return ranked[:k]


def render_markdown(matches: List[Match]) -> str:
    if not matches:
        return "No related historical decisions found for this change."
    lines = ["### Historical decisions related to this change", ""]
    for m in matches:
        d = m.decision
        flag = {"rejected": "REJECTED earlier", "accepted": "Accepted", "deferred": "Deferred", "open": "Unresolved"}[d.status]
        lines.append(f"**[{flag}] {d.title}** (`{d.decision_id}`, relevance {m.score:.1f})")
        lines.append(f"- why surfaced: {'; '.join(m.reasons)}")
        for r in d.reasons[:2]:
            ev = r.evidence[0].url if r.evidence else d.source_url
            lines.append(f"- reason: {r.text} ([source]({ev}))")
        if d.evidence:
            lines.append(f"- evidence: [{d.evidence[0].author}]({d.evidence[0].url}): \"{d.evidence[0].quote}\"")
        lines.append("")
    return "\n".join(lines)
