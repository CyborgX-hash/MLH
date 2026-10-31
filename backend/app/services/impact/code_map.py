"""Decision-to-code mapping.

A decision is connected to code only through change records: a merged pull request (or a commit) that the
decision cites, that is explicitly linked to the decision's sources ("closes #12", "(#25)", merge commit),
or (as a *possible* mapping) one linked by a possible relationship. File contents are never searched for
keywords. Renames and deletions are followed through later merged pull requests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Commit, Decision, DecisionCodeLink, PullRequest, PullRequestFile, Repository
from app.services.linking.history import Key, decision_records, links_touching

NO_EVIDENCE = "No verified implementation evidence found."


@dataclass
class Candidate:
    status: str  # verified | possible
    basis: List[str] = field(default_factory=list)


def _follow(path: str, since: Optional[datetime], later: List[Tuple[PullRequest, List[PullRequestFile]]]):
    """Track a path through later merged PRs: (current path or None if deleted, deleted?, PR numbers that changed it)."""
    cur, changed = path, []
    for pr, files in later:
        if since and pr.gh_merged_at and pr.gh_merged_at <= since:
            continue
        for f in files:
            if f.status == "renamed" and f.previous_filename == cur:
                cur = f.filename
                changed.append(pr.number)
                break
            if f.filename == cur and f.status == "removed":
                changed.append(pr.number)
                return None, True, changed
            if f.filename == cur:
                changed.append(pr.number)
                break
    return cur, False, changed


def map_decision(db: Session, d: Decision) -> Dict:
    repo = db.get(Repository, d.repository_id)
    cited = decision_records(db, d.id)
    prs: Dict[int, Candidate] = {}
    commits: Dict[int, Candidate] = {}

    def note(table: Dict[int, Candidate], rid: int, status: str, why: str) -> None:
        c = table.setdefault(rid, Candidate(status))
        if status == "verified":
            c.status = "verified"
        c.basis.append(why)

    for kind, rid in cited:
        if kind == "pull_request":
            note(prs, rid, "verified", "cited as decision evidence")
        elif kind == "commit":
            note(commits, rid, "verified", "cited as decision evidence")
    for link in links_touching(db, d.repository_id, cited):
        src: Key = (link.source_kind, link.source_id)
        tgt: Key = (link.target_kind, link.target_id)
        other = tgt if src in cited else src
        if other in cited:
            continue
        explicit = link.verification_status == "verified" and (
            link.relation == "implements" or link.signal in ("commit_reference", "linked_pr_metadata"))
        status = "verified" if explicit else "possible"
        why = f"{link.relation} via {link.signal.replace('_', ' ')}"
        if other[0] == "pull_request":
            note(prs, other[1], status, why)
        elif other[0] == "commit":
            note(commits, other[1], status, why)
    # A verified PR's merge commit and commits naming it are part of the same implementation.
    for pr_id, cand in list(prs.items()):
        pr = db.get(PullRequest, pr_id)
        if pr and pr.merge_commit_sha:
            c = db.scalar(select(Commit).where(Commit.repository_id == repo.id, Commit.sha == pr.merge_commit_sha))
            if c and c.id not in commits:
                commits[c.id] = Candidate(cand.status, [f"merge commit of PR #{pr.number}"])

    merged = [
        (pr, list(db.scalars(select(PullRequestFile).where(PullRequestFile.pull_request_id == pr.id))))
        for pr in db.scalars(
            select(PullRequest).where(PullRequest.repository_id == repo.id, PullRequest.gh_merged_at.is_not(None))
            .order_by(PullRequest.gh_merged_at)
        )
    ]
    rows: List[DecisionCodeLink] = []
    notes: List[str] = []
    pr_commit = {}
    for cid, cand in commits.items():
        c = db.get(Commit, cid)
        for pr_id in prs:
            p = db.get(PullRequest, pr_id)
            if p and p.merge_commit_sha == c.sha:
                pr_commit[pr_id] = c
    for pr_id, cand in prs.items():
        pr = db.get(PullRequest, pr_id)
        if pr is None:
            continue
        if pr.gh_merged_at is None:
            notes.append(f"PR #{pr.number} is linked but was never merged, so it is not an implementation.")
            continue
        c = pr_commit.get(pr_id)
        commit_sha = pr.merge_commit_sha
        commit_url = c.html_url if c else (f"{repo.html_url}/commit/{commit_sha}" if commit_sha else None)
        files = next((fs for p, fs in merged if p.id == pr.id), [])
        if not files:
            notes.append(f"PR #{pr.number}: changed files were not ingested.")
            rows.append(DecisionCodeLink(decision_id=d.id, link_status=cand.status, basis="; ".join(cand.basis),
                                         pull_request_id=pr.id, pr_number=pr.number, pr_url=pr.html_url,
                                         merged_at=pr.gh_merged_at, commit_sha=commit_sha, commit_url=commit_url))
            continue
        for f in files:
            if f.status == "removed":
                current, deleted, changed = None, True, []
            else:
                current, deleted, changed = _follow(f.filename, pr.gh_merged_at, merged)
            rows.append(DecisionCodeLink(
                decision_id=d.id, link_status=cand.status, basis="; ".join(cand.basis), pull_request_id=pr.id,
                pr_number=pr.number, pr_url=pr.html_url, merged_at=pr.gh_merged_at, commit_sha=commit_sha,
                commit_url=commit_url, path=f.filename, change_type=f.status, current_path=current,
                deleted=deleted, changed_after=changed,
            ))
    covered = {c.sha for c in pr_commit.values()}
    for cid, cand in commits.items():
        c = db.get(Commit, cid)
        if c is None or c.sha in covered:
            continue
        rows.append(DecisionCodeLink(decision_id=d.id, link_status=cand.status, basis="; ".join(cand.basis),
                                     commit_sha=c.sha, commit_url=c.html_url, merged_at=c.committed_at))
        notes.append(f"Commit {c.sha[:7]}: per-commit file lists are not ingested; see the commit on GitHub.")

    db.execute(delete(DecisionCodeLink).where(DecisionCodeLink.decision_id == d.id))
    db.add_all(rows)
    db.commit()
    return summary(db, d, notes)


def summary(db: Session, d: Decision, notes: Optional[List[str]] = None) -> Dict:
    rows = list(db.scalars(select(DecisionCodeLink).where(DecisionCodeLink.decision_id == d.id)
                           .order_by(DecisionCodeLink.link_status.desc(), DecisionCodeLink.pr_number, DecisionCodeLink.path)))
    verified = [r for r in rows if r.link_status == "verified"]
    return {
        "decision_id": d.id,
        "message": None if verified else NO_EVIDENCE,
        "verified": verified,
        "possible": [r for r in rows if r.link_status == "possible"],
        "notes": notes or [],
    }
