"""Build the relationship graph between a repository's records.

Verified links come only from explicit evidence: references (#N, URLs), closing keywords, "supersedes" /
"reverts" statements, commit messages naming a PR, and PR merge-commit metadata.
Possible links come from shared file paths, shared rare technical terms and text similarity. They are
never upgraded to verified, and text similarity alone yields only a low-confidence "related_to".
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Comment, Commit, Discussion, Issue, PullRequest, PullRequestFile, Repository, SourceLink
from app.services.evidence.text import STOPWORDS
from app.services.linking.refs import find_refs, mentioned_paths, pr_number_in_commit, reverted_sha, strip_code

Key = Tuple[str, int]  # (kind, db id)
MAX_POSSIBLE_PER_RECORD = 3
TERMINOLOGY_MIN_SHARED = 2
SEMANTIC_MIN = 0.45


@dataclass
class Text:
    record: Key
    text: str
    url: str


class Graph:
    def __init__(self, db: Session, repo: Repository):
        self.db, self.repo = db, repo
        rid = repo.id
        self.issues = {i.number: i for i in db.scalars(select(Issue).where(Issue.repository_id == rid))}
        self.prs = {p.number: p for p in db.scalars(select(PullRequest).where(PullRequest.repository_id == rid))}
        self.discussions = {d.number: d for d in db.scalars(select(Discussion).where(Discussion.repository_id == rid))}
        self.commits = {c.sha.lower(): c for c in db.scalars(select(Commit).where(Commit.repository_id == rid))}
        self.links: Dict[Tuple[Key, Key, str, str], SourceLink] = {}

    def by_number(self, n: int) -> Optional[Key]:
        # Issues, pull requests and discussions share one number space per repository.
        if n in self.prs:
            return ("pull_request", self.prs[n].id)
        if n in self.issues:
            return ("issue", self.issues[n].id)
        if n in self.discussions:
            return ("discussion", self.discussions[n].id)
        return None  # unknown number: never invent a link

    def parent(self, kind: str, number: int) -> Optional[Key]:
        table = {"issue": self.issues, "pull_request": self.prs, "discussion": self.discussions}[kind]
        rec = table.get(number)
        return (kind, rec.id) if rec else None

    def add(self, src: Key, tgt: Key, relation: str, signal: str, status: str, confidence: float, evidence: dict):
        if src == tgt:
            return
        key = (src, tgt, relation, signal)
        if key in self.links and self.links[key].confidence >= confidence:
            return
        self.links[key] = SourceLink(
            repository_id=self.repo.id, source_kind=src[0], source_id=src[1], target_kind=tgt[0], target_id=tgt[1],
            relation=relation, signal=signal, verification_status=status, confidence=round(confidence, 3),
            evidence=evidence,
        )

    def texts(self) -> Iterable[Text]:
        for i in self.issues.values():
            yield Text(("issue", i.id), f"{i.title}\n{i.body or ''}", i.html_url)
        for p in self.prs.values():
            yield Text(("pull_request", p.id), f"{p.title}\n{p.body or ''}", p.html_url)
        for d in self.discussions.values():
            yield Text(("discussion", d.id), f"{d.title}\n{d.body or ''}", d.html_url)
        for c in self.db.scalars(select(Comment).where(Comment.repository_id == self.repo.id)):
            parent = self.parent(c.parent_kind, c.parent_number)
            if parent and c.body:
                yield Text(parent, c.body, c.html_url)
        for c in self.commits.values():
            yield Text(("commit", c.id), c.message, c.html_url)


def _explicit(g: Graph) -> None:
    for t in g.texts():
        own_pr = pr_number_in_commit(t.text) if t.record[0] == "commit" else None
        for ref in find_refs(t.text, g.repo.owner, g.repo.name):
            target = g.by_number(ref.number)
            if target is None:
                continue
            if ref.number == own_pr and ref.relation == "references":
                continue  # "(#25)" in a squash commit is recorded once, as a commit_reference below
            relation = ref.relation
            if relation == "implements" and t.record[0] not in ("pull_request", "commit"):
                relation = "references"  # only code changes implement; an issue saying "fixes #3" just refers
            if relation == "references" and t.record[0] == "discussion":
                relation = "discusses"
            src, tgt = (target, t.record) if ref.reverse else (t.record, target)
            g.add(src, tgt, relation, ref.signal, "verified", 1.0, {"snippet": ref.snippet, "url": t.url})

    for c in g.commits.values():
        n = pr_number_in_commit(c.message)
        if n and n in g.prs:
            g.add(("commit", c.id), ("pull_request", g.prs[n].id), "references", "commit_reference", "verified", 1.0,
                  {"snippet": c.message.split("\n", 1)[0][:200], "url": c.html_url})
        sha = reverted_sha(c.message)
        if sha:
            target = next((x for s, x in g.commits.items() if s.startswith(sha)), None)
            if target:
                g.add(("commit", c.id), ("commit", target.id), "conflicts_with", "explicit_reference", "verified", 1.0,
                      {"snippet": f"reverts {sha[:12]}", "url": c.html_url})
    for p in g.prs.values():
        if p.merge_commit_sha and p.merge_commit_sha.lower() in g.commits:
            c = g.commits[p.merge_commit_sha.lower()]
            g.add(("commit", c.id), ("pull_request", p.id), "references", "linked_pr_metadata", "verified", 1.0,
                  {"snippet": f"merge commit of PR #{p.number}", "url": p.html_url})


def _shared_files(g: Graph, verified: Set[frozenset]) -> None:
    touched: Dict[str, Set[int]] = defaultdict(set)  # path -> PR numbers
    rows = g.db.execute(
        select(PullRequestFile.filename, PullRequestFile.previous_filename, PullRequest.number)
        .join(PullRequest, PullRequestFile.pull_request_id == PullRequest.id)
        .where(PullRequest.repository_id == g.repo.id)
    )
    for filename, previous, number in rows:
        for path in filter(None, (filename, previous)):
            touched[path].add(number)
    if not touched:
        return
    for t in g.texts():
        if t.record[0] in ("pull_request", "commit"):
            continue
        for path in mentioned_paths(t.text):  # paths in `code` spans count: that is how people quote them
            for n in touched.get(path, ()):
                if frozenset((t.record, ("pull_request", g.prs[n].id))) in verified:
                    continue
                g.add(t.record, ("pull_request", g.prs[n].id), "related_to", "shared_files", "possible", 0.5,
                      {"paths": [path], "url": t.url})


def _terms(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-z][a-z0-9_+#-]{2,}", strip_code(text).lower()) if w not in STOPWORDS]


def _similarity(g: Graph, verified: Set[frozenset]) -> None:
    docs: Dict[Key, Counter] = {}
    urls: Dict[Key, str] = {}
    for kind, table in (("issue", g.issues), ("pull_request", g.prs), ("discussion", g.discussions)):
        for rec in table.values():
            docs[(kind, rec.id)] = Counter(_terms(f"{rec.title} {rec.title} {rec.body or ''}"))
            urls[(kind, rec.id)] = rec.html_url
    n = len(docs)
    if n < 2:
        return
    df: Counter = Counter()
    for c in docs.values():
        df.update(c.keys())
    rare_cut = max(3, int(0.05 * n))  # a term in at most 5% of records (or 3) is distinctive
    idf = {t: math.log((1 + n) / (1 + d)) + 1 for t, d in df.items()}
    index: Dict[str, List[Key]] = defaultdict(list)
    for key, c in docs.items():
        for t in c:
            if df[t] <= rare_cut:
                index[t].append(key)
    vec = {}
    for key, c in docs.items():
        v = {t: tf * idf[t] for t, tf in c.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vec[key] = {t: x / norm for t, x in v.items()}

    shared: Dict[Tuple[Key, Key], Set[str]] = defaultdict(set)
    for term, keys in index.items():
        for i, a in enumerate(keys):
            for b in keys[i + 1 :]:
                shared[(a, b) if a < b else (b, a)].add(term)

    best: Dict[Key, List[Tuple[float, Key, str, Set[str]]]] = defaultdict(list)
    for (a, b), terms in shared.items():
        if frozenset((a, b)) in verified:
            continue
        cos = sum(x * vec[b].get(t, 0.0) for t, x in vec[a].items())
        if len(terms) >= TERMINOLOGY_MIN_SHARED:
            best[a].append((0.3 + 0.3 * min(cos, 1.0), b, "terminology", terms))
        elif cos >= SEMANTIC_MIN:
            best[a].append((0.2 * cos, b, "semantic_similarity", terms))
    for a, cands in best.items():
        for conf, b, signal, terms in sorted(cands, key=lambda x: -x[0])[:MAX_POSSIBLE_PER_RECORD]:
            g.add(a, b, "related_to", signal, "possible", conf,
                  {"terms": sorted(terms)[:8], "url": urls[b]})


def rebuild_links(db: Session, repo: Repository) -> Dict[str, int]:
    """Recompute every link for the repository. Deterministic and idempotent."""
    g = Graph(db, repo)
    _explicit(g)
    verified = {frozenset((k[0], k[1])) for k in g.links}
    _shared_files(g, verified)
    _similarity(g, verified)
    db.execute(delete(SourceLink).where(SourceLink.repository_id == repo.id))
    db.add_all(g.links.values())
    db.flush()
    counts = Counter(link.verification_status for link in g.links.values())
    return {"verified": counts.get("verified", 0), "possible": counts.get("possible", 0)}
