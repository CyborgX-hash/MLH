"""Core data structures shared by every pipeline stage."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

STATUSES = ("accepted", "rejected", "deferred", "open")


@dataclass
class Post:
    post_id: int
    author: str
    created_at: str
    text: str
    url: str
    reply_to: Optional[int] = None


@dataclass
class Thread:
    source: str
    url: str
    title: str
    posts: List[Post] = field(default_factory=list)

    def post(self, post_id: int) -> Optional[Post]:
        for p in self.posts:
            if p.post_id == post_id:
                return p
        return None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Thread":
        return cls(
            source=data["source"],
            url=data["url"],
            title=data["title"],
            posts=[Post(**p) for p in data["posts"]],
        )


@dataclass
class Evidence:
    """A span of an original post that supports a claim."""

    post_id: int
    author: str
    url: str
    quote: str
    verbatim: bool = True


@dataclass
class Reason:
    text: str
    evidence: List[Evidence] = field(default_factory=list)


@dataclass
class CodeRef:
    path: str
    symbol: str = ""
    line: int = 0
    kind: str = "mention"  # "definition" | "mention" | "file"
    commit: str = ""


@dataclass
class Decision:
    decision_id: str
    title: str
    status: str
    summary: str
    reasons: List[Reason] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    code_refs: List[CodeRef] = field(default_factory=list)
    source_url: str = ""
    source_title: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Decision":
        return cls(
            decision_id=d["decision_id"],
            title=d["title"],
            status=d["status"],
            summary=d.get("summary", ""),
            reasons=[
                Reason(r["text"], [Evidence(**e) for e in r.get("evidence", [])])
                for r in d.get("reasons", [])
            ],
            evidence=[Evidence(**e) for e in d.get("evidence", [])],
            code_refs=[CodeRef(**c) for c in d.get("code_refs", [])],
            source_url=d.get("source_url", ""),
            source_title=d.get("source_title", ""),
        )

    def search_text(self) -> str:
        parts = [self.title, self.summary] + [r.text for r in self.reasons]
        return " ".join(p for p in parts if p)


def decision_id(source_url: str, title: str) -> str:
    """Deterministic ID: the same thread and idea always map to the same record."""
    norm = re.sub(r"\W+", " ", title.lower()).strip()
    digest = hashlib.sha1(f"{source_url}|{norm}".encode("utf-8")).hexdigest()[:10]
    return f"DEC-{digest}"
