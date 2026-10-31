"""Blind evaluation against Python PEPs.

The pipeline only ever sees the public discussion. The PEP's own "Rejected Ideas" section is the
hidden ground truth: we check which rejected ideas the system recovered, and whether it recovered
the reasons too.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from decisionlens.ingest import http_get, topic_key
from decisionlens.models import Decision
from decisionlens.text import cosine_sets, token_set

PEP_RAW = "https://raw.githubusercontent.com/python/peps/main/peps/pep-{num:04d}.rst"
REJECTED_HEADINGS = {
    "rejected ideas",
    "rejected alternatives",
    "rejected proposals",
    "rejected design alternatives",
    "alternatives considered",
    "rejected features",
    "rejected suggestions",
}
UNDERLINE = re.compile(r"^([=\-~^\"'`#*+:._])\1{2,}\s*$")
DISCOURSE_URL = re.compile(r"https://discuss\.python\.org/t/[\w.%-]+/\d+")


@dataclass
class GroundTruthItem:
    title: str
    body: str

    @property
    def tokens(self):
        return token_set(self.title + " " + self.body)


def fetch_pep(num: int) -> str:
    return http_get(PEP_RAW.format(num=num), as_json=False)


def pep_discussion_urls(pep_text: str) -> List[str]:
    header = pep_text.split("\n\n", 1)[0]
    seen, urls = set(), []
    for url in DISCOURSE_URL.findall(header):
        key = topic_key(url)
        if key not in seen:
            seen.add(key)
            urls.append(url)
    return urls


def pep_title(pep_text: str) -> str:
    m = re.search(r"^Title:\s*(.+)$", pep_text, re.M)
    return m.group(1).strip() if m else ""


def _heading_at(lines: List[str], i: int) -> Optional[Tuple[str, str]]:
    if i + 1 < len(lines) and lines[i].strip() and UNDERLINE.match(lines[i + 1]) and not UNDERLINE.match(lines[i]):
        if len(lines[i + 1].strip()) >= len(lines[i].strip()) - 1:
            return lines[i].strip(), lines[i + 1].strip()[0]
    return None


def parse_rejected_ideas(pep_text: str) -> List[GroundTruthItem]:
    lines = pep_text.splitlines()
    start, char = None, None
    for i in range(len(lines)):
        h = _heading_at(lines, i)
        if h and h[0].lower() in REJECTED_HEADINGS:
            start, char = i + 2, h[1]
            break
    if start is None:
        return []
    end = len(lines)
    for j in range(start, len(lines)):
        h = _heading_at(lines, j)
        if h and h[1] == char:
            end = j
            break
    section = lines[start:end]

    items: List[GroundTruthItem] = []
    sub_starts = [k for k in range(len(section)) if _heading_at(section, k)]
    if sub_starts:
        for n, k in enumerate(sub_starts):
            stop = sub_starts[n + 1] if n + 1 < len(sub_starts) else len(section)
            body = " ".join(l.strip() for l in section[k + 2 : stop] if l.strip())
            items.append(GroundTruthItem(section[k].strip(), body))
    else:
        for para in re.split(r"\n\s*\n", "\n".join(section)):
            text = " ".join(para.split())
            if len(text) > 40:
                items.append(GroundTruthItem(re.split(r"(?<=[.:])\s", text, 1)[0][:100], text))
    return [i for i in items if i.body or i.title]


def _decision_tokens(d: Decision):
    return token_set(d.title + " " + d.summary), token_set(" ".join(r.text for r in d.reasons))


@dataclass
class Match:
    truth: str
    decision: str
    idea_score: float
    reason_score: float


@dataclass
class Report:
    pep: int
    truth_count: int
    predicted_rejected: int
    matches: List[Match] = field(default_factory=list)
    missed: List[str] = field(default_factory=list)
    threshold: float = 0.2

    @property
    def recall(self) -> float:
        return len(self.matches) / self.truth_count if self.truth_count else 0.0

    @property
    def precision(self) -> float:
        return len(self.matches) / self.predicted_rejected if self.predicted_rejected else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    @property
    def reason_score(self) -> float:
        return sum(m.reason_score for m in self.matches) / len(self.matches) if self.matches else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pep": self.pep,
            "ground_truth_rejected_ideas": self.truth_count,
            "predicted_rejected_decisions": self.predicted_rejected,
            "recovered": len(self.matches),
            "recall": round(self.recall, 3),
            "precision": round(self.precision, 3),
            "f1": round(self.f1, 3),
            "reason_overlap": round(self.reason_score, 3),
            "match_threshold": self.threshold,
            "matches": [
                {
                    "ground_truth": m.truth,
                    "recovered_decision": m.decision,
                    "idea_similarity": round(m.idea_score, 3),
                    "reason_similarity": round(m.reason_score, 3),
                }
                for m in self.matches
            ],
            "missed": self.missed,
        }


def score(pep: int, truth: List[GroundTruthItem], decisions: List[Decision], threshold: float = 0.2) -> Report:
    predicted = [d for d in decisions if d.status == "rejected"]
    pairs = []
    for ti, t in enumerate(truth):
        tt = t.tokens
        for di, d in enumerate(predicted):
            idea_tok, reason_tok = _decision_tokens(d)
            sim = cosine_sets(tt, idea_tok | reason_tok)
            if sim >= threshold:
                pairs.append((sim, ti, di))
    pairs.sort(reverse=True)
    used_t, used_d = set(), set()
    report = Report(pep, len(truth), len(predicted), threshold=threshold)
    for sim, ti, di in pairs:
        if ti in used_t or di in used_d:
            continue
        used_t.add(ti)
        used_d.add(di)
        t, d = truth[ti], predicted[di]
        _, reason_tok = _decision_tokens(d)
        reason_sim = cosine_sets(t.tokens, reason_tok) if reason_tok else 0.0
        report.matches.append(Match(t.title, d.title, sim, reason_sim))
    report.missed = [t.title for i, t in enumerate(truth) if i not in used_t]
    return report
