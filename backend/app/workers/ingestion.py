"""Repository ingestion job.

Runs stage by stage, commits after each stage so progress is visible, and keeps going when a
non-essential stage fails (the job ends as "partial"). Only a failed metadata stage fails the job.

Independent of FastAPI: it takes a session factory and a client factory, so it can be called from
BackgroundTasks today and from Celery or another worker later.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.upsert import upsert
from app.models import Comment, Commit, Discussion, Issue, PullRequest, PullRequestFile, Repository, SourceFile, SyncJob
from app.services.github.client import GitHubClient
from app.services.github.errors import BinaryFile, FileTooLarge, GitHubError, GraphQLUnavailable, InvalidPath, RateLimited
from app.services.github.files import select_files

log = logging.getLogger(__name__)

STAGES = ["metadata", "issues", "issue_comments", "pull_requests", "discussions", "commits", "code"]
STAGE_LABELS = {
    "queued": "Waiting to start",
    "metadata": "Repository connected",
    "issues": "Fetching issues",
    "issue_comments": "Fetching issue comments",
    "pull_requests": "Fetching pull requests",
    "discussions": "Fetching discussions",
    "commits": "Fetching commits",
    "code": "Fetching code",
    "done": "Processing completed",
    "failed": "Processing failed",
}
ACTIVE = ("queued", "running")
# Overlap applied to incremental cursors so clock skew between GitHub and us never loses an update.
CURSOR_SKEW = timedelta(minutes=2)


@dataclass(frozen=True)
class Limits:
    issues: int
    issue_comments: int
    pull_requests: int
    pr_details: int  # PRs whose reviews and files are fetched (2 extra requests each)
    review_comments: int
    discussions: int
    commits: int
    files: int
    file_bytes: int = 200_000

    @classmethod
    def for_token(cls, has_token: bool) -> "Limits":
        if has_token:  # 5,000 requests/hour
            return cls(issues=1000, issue_comments=5000, pull_requests=500, pr_details=300,
                       review_comments=5000, discussions=200, commits=1000, files=300)
        # Unauthenticated GitHub allows 60 requests/hour; this preset stays around 50 for a full sync.
        return cls(issues=100, issue_comments=300, pull_requests=30, pr_details=10,
                   review_comments=300, discussions=0, commits=100, files=15)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ts(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def login(user: Optional[dict]) -> Optional[str]:
    return (user or {}).get("login")


def number_from_url(url: str) -> int:
    return int(url.rstrip("/").rsplit("/", 1)[-1])


def repository_fields(data: dict) -> Dict[str, Any]:
    """Map GitHub repository JSON to Repository columns."""
    return {
        "github_id": data["id"],
        "node_id": data["node_id"],
        "owner": data["owner"]["login"],
        "name": data["name"],
        "full_name": data["full_name"],
        "html_url": data["html_url"],
        "description": data.get("description"),
        "default_branch": data.get("default_branch") or "main",
        "language": data.get("language"),
        "license_spdx": (data.get("license") or {}).get("spdx_id"),
        "stars": data.get("stargazers_count", 0),
        "forks": data.get("forks_count", 0),
        "archived": bool(data.get("archived")),
        "has_issues": bool(data.get("has_issues", True)),
        "has_discussions": bool(data.get("has_discussions")),
        "gh_created_at": ts(data.get("created_at")),
        "gh_pushed_at": ts(data.get("pushed_at")),
    }


class Sync:
    def __init__(self, db: Session, gh: GitHubClient, repo: Repository, job: SyncJob, limits: Limits):
        self.db, self.gh, self.repo, self.job, self.limits = db, gh, repo, job, limits
        self.o, self.r = repo.owner, repo.name
        self.cursors: Dict[str, str] = {} if job.full else dict(repo.sync_cursors or {})

    # ------------------------------------------------------------------ stages

    def metadata(self) -> Dict[str, Any]:
        data = self.gh.get_repository(self.o, self.r)
        for key, value in repository_fields(data).items():
            setattr(self.repo, key, value)
        self.o, self.r = self.repo.owner, self.repo.name  # follow renames and transfers
        return {"default_branch": self.repo.default_branch}

    def issues(self) -> Dict[str, Any]:
        if not self.repo.has_issues:
            return {"skipped": "Issues are disabled for this repository."}
        rows = [
            {
                "repository_id": self.repo.id, "github_id": i["id"], "node_id": i["node_id"], "number": i["number"],
                "title": i["title"], "body": i.get("body"), "state": i["state"], "state_reason": i.get("state_reason"),
                "author_login": login(i.get("user")), "author_association": i.get("author_association"),
                "labels": [lb["name"] for lb in i.get("labels", []) if isinstance(lb, dict)],
                "comments_count": i.get("comments", 0), "html_url": i["html_url"],
                "gh_created_at": ts(i.get("created_at")), "gh_updated_at": ts(i.get("updated_at")),
                "gh_closed_at": ts(i.get("closed_at")),
            }
            for i in self.gh.get_issues(self.o, self.r, since=self.cursors.get("issues"), limit=self.limits.issues)
        ]
        upsert(self.db, Issue, rows, ["repository_id", "number"])
        return {"fetched": len(rows), "truncated": len(rows) >= self.limits.issues}

    def issue_comments(self) -> Dict[str, Any]:
        rows = []
        for c in self.gh.get_issue_comments(
            self.o, self.r, since=self.cursors.get("issue_comments"), limit=self.limits.issue_comments
        ):
            # Conversation comments on a PR come from the issues API too; the URL tells them apart.
            on_pr = "/pull/" in c["html_url"]
            rows.append(self._comment(c, "issue_comment", "pull_request" if on_pr else "issue", number_from_url(c["issue_url"])))
        upsert(self.db, Comment, rows, ["repository_id", "node_id"])
        return {"fetched": len(rows), "truncated": len(rows) >= self.limits.issue_comments}

    def pull_requests(self) -> Dict[str, Any]:
        counts = {"fetched": 0, "details_fetched": 0, "details_unchanged": 0, "reviews": 0, "files": 0}
        prs = list(
            self.gh.get_pull_requests(
                self.o, self.r, updated_since=self.cursors.get("pull_requests"), limit=self.limits.pull_requests
            )
        )
        rows = [
            {
                "repository_id": self.repo.id, "github_id": p["id"], "node_id": p["node_id"], "number": p["number"],
                "title": p["title"], "body": p.get("body"), "state": p["state"], "draft": bool(p.get("draft")),
                "author_login": login(p.get("user")), "author_association": p.get("author_association"),
                "labels": [lb["name"] for lb in p.get("labels", []) if isinstance(lb, dict)],
                "base_ref": (p.get("base") or {}).get("ref"), "head_ref": (p.get("head") or {}).get("ref"),
                "head_sha": (p.get("head") or {}).get("sha"), "merge_commit_sha": p.get("merge_commit_sha"),
                "html_url": p["html_url"], "gh_created_at": ts(p.get("created_at")),
                "gh_updated_at": ts(p.get("updated_at")), "gh_closed_at": ts(p.get("closed_at")),
                "gh_merged_at": ts(p.get("merged_at")),
            }
            for p in prs
        ]
        upsert(self.db, PullRequest, rows, ["repository_id", "number"])
        counts["fetched"] = len(rows)
        counts["truncated"] = len(rows) >= self.limits.pull_requests

        stored = {
            pr.number: pr
            for pr in self.db.scalars(
                select(PullRequest).where(PullRequest.repository_id == self.repo.id, PullRequest.number.in_([p["number"] for p in prs]))
            )
        }
        for p in prs[: self.limits.pr_details]:
            pr = stored[p["number"]]
            if pr.details_updated_at and pr.details_updated_at == pr.gh_updated_at:
                counts["details_unchanged"] += 1  # nothing changed since the last fetch: skip 2 requests
                continue
            reviews = [
                self._comment(rv, "review", "pull_request", pr.number, review_state=rv.get("state"),
                              commit_sha=rv.get("commit_id"), created=rv.get("submitted_at"))
                for rv in self.gh.get_pull_request_reviews(self.o, self.r, pr.number)
            ]
            upsert(self.db, Comment, reviews, ["repository_id", "node_id"])
            files = [
                {
                    "pull_request_id": pr.id, "filename": f["filename"], "previous_filename": f.get("previous_filename"),
                    "status": f["status"], "additions": f.get("additions", 0), "deletions": f.get("deletions", 0),
                    "blob_sha": f.get("sha"),
                }
                for f in self.gh.get_pull_request_files(self.o, self.r, pr.number)
            ]
            self.db.execute(delete(PullRequestFile).where(PullRequestFile.pull_request_id == pr.id))
            upsert(self.db, PullRequestFile, files, ["pull_request_id", "filename"])
            pr.details_updated_at = pr.gh_updated_at
            counts["details_fetched"] += 1
            counts["reviews"] += len(reviews)
            counts["files"] += len(files)

        review_comments = [
            self._comment(c, "review_comment", "pull_request", number_from_url(c["pull_request_url"]),
                          path=c.get("path"), line=c.get("line") or c.get("original_line"),
                          commit_sha=c.get("commit_id"),
                          in_reply_to=str(c["in_reply_to_id"]) if c.get("in_reply_to_id") else None)
            for c in self.gh.get_pull_request_review_comments(
                self.o, self.r, since=self.cursors.get("pull_requests"), limit=self.limits.review_comments
            )
        ]
        upsert(self.db, Comment, review_comments, ["repository_id", "node_id"])
        counts["review_comments"] = len(review_comments)
        return counts

    def discussions(self) -> Dict[str, Any]:
        if not self.repo.has_discussions:
            return {"skipped": "Discussions are not enabled for this repository."}
        if not self.gh.has_token:
            return {"skipped": "GitHub Discussions need the GraphQL API, which requires GITHUB_TOKEN."}
        if self.limits.discussions == 0:
            return {"skipped": "Discussion limit is 0."}
        count = comments = 0
        for d in self.gh.get_discussions(
            self.o, self.r, updated_since=self.cursors.get("discussions"), limit=self.limits.discussions
        ):
            upsert(self.db, Discussion, [{
                "repository_id": self.repo.id, "github_id": d.get("databaseId"), "node_id": d["id"],
                "number": d["number"], "title": d["title"], "body": d.get("body"),
                "category": (d.get("category") or {}).get("name"), "author_login": login(d.get("author")),
                "answer_node_id": (d.get("answer") or {}).get("id"), "closed": bool(d.get("closed")),
                "html_url": d["url"], "gh_created_at": ts(d.get("createdAt")), "gh_updated_at": ts(d.get("updatedAt")),
                "gh_closed_at": ts(d.get("closedAt")),
            }], ["repository_id", "number"])
            rows = [
                {
                    "repository_id": self.repo.id, "github_id": c.get("databaseId"), "node_id": c["id"],
                    "kind": "discussion_reply" if c.get("reply_to") else "discussion_comment",
                    "parent_kind": "discussion", "parent_number": d["number"], "author_login": login(c.get("author")),
                    "author_association": c.get("authorAssociation"), "body": c.get("body"), "review_state": None,
                    "path": None, "line": None, "commit_sha": None, "in_reply_to": c.get("reply_to"),
                    "html_url": c["url"], "gh_created_at": ts(c.get("createdAt")), "gh_updated_at": ts(c.get("updatedAt")),
                }
                for c in self.gh.get_discussion_comments(d["id"])
            ]
            upsert(self.db, Comment, rows, ["repository_id", "node_id"])
            count += 1
            comments += len(rows)
        return {"fetched": count, "comments": comments, "truncated": count >= self.limits.discussions}

    def commits(self) -> Dict[str, Any]:
        rows = []
        for c in self.gh.get_commits(
            self.o, self.r, sha=self.repo.default_branch, since=self.cursors.get("commits"), limit=self.limits.commits
        ):
            meta = c.get("commit") or {}
            rows.append({
                "repository_id": self.repo.id, "sha": c["sha"], "message": meta.get("message", ""),
                "author_login": login(c.get("author")), "author_name": (meta.get("author") or {}).get("name"),
                "author_email": (meta.get("author") or {}).get("email"), "committer_login": login(c.get("committer")),
                "parents": [p["sha"] for p in c.get("parents", [])], "html_url": c["html_url"],
                "authored_at": ts((meta.get("author") or {}).get("date")),
                "committed_at": ts((meta.get("committer") or {}).get("date")),
            })
        upsert(self.db, Commit, rows, ["repository_id", "sha"])
        return {"fetched": len(rows), "truncated": len(rows) >= self.limits.commits}

    def code(self) -> Dict[str, Any]:
        branch = self.repo.default_branch
        tree = self.gh.get_repository_tree(self.o, self.r, branch)
        selected, skipped = select_files(tree.get("tree", []), self.limits.files, self.limits.file_bytes)
        existing = {
            f.path: f for f in self.db.scalars(select(SourceFile).where(SourceFile.repository_id == self.repo.id))
        }
        counts: Dict[str, Any] = {"selected": len(selected), "fetched": 0, "unchanged": 0, "not_text": 0,
                                  "excluded": skipped, "tree_truncated": bool(tree.get("truncated"))}
        for f in selected:
            old = existing.get(f.path)
            if old and old.blob_sha == f.sha and (old.content is not None or old.skipped_reason):
                counts["unchanged"] += 1  # same blob SHA: content cannot have changed
                continue
            content, reason = None, None
            try:
                content = self.gh.get_file_content(self.o, self.r, f.path, ref=branch, max_bytes=self.limits.file_bytes)
                counts["fetched"] += 1
            except (BinaryFile, FileTooLarge, InvalidPath) as exc:
                reason = exc.__class__.__name__
                counts["not_text"] += 1
            upsert(self.db, SourceFile, [{
                "repository_id": self.repo.id, "path": f.path, "blob_sha": f.sha, "size": f.size,
                "language": f.language, "priority": f.priority, "content": content, "skipped_reason": reason,
                "html_url": f"{self.repo.html_url}/blob/{branch}/{f.path}", "fetched_at": utcnow(),
            }], ["repository_id", "path"])
        if not tree.get("truncated"):
            keep = [f.path for f in selected]
            self.db.execute(
                delete(SourceFile).where(SourceFile.repository_id == self.repo.id, SourceFile.path.not_in(keep))
            )
        return counts

    # ------------------------------------------------------------------ helpers

    def _comment(self, c: dict, kind: str, parent_kind: str, number: int, review_state=None, path=None,
                 line=None, commit_sha=None, in_reply_to=None, created=None) -> Dict[str, Any]:
        return {
            "repository_id": self.repo.id, "github_id": c.get("id"), "node_id": c["node_id"], "kind": kind,
            "parent_kind": parent_kind, "parent_number": number, "author_login": login(c.get("user")),
            "author_association": c.get("author_association"), "body": c.get("body"), "review_state": review_state,
            "path": path, "line": line, "commit_sha": commit_sha, "in_reply_to": in_reply_to,
            "html_url": c["html_url"], "gh_created_at": ts(created or c.get("created_at")),
            "gh_updated_at": ts(c.get("updated_at") or created or c.get("created_at")),
        }


def _set(job: SyncJob, stage: str, entry: Dict[str, Any]) -> None:
    job.progress = {**(job.progress or {}), stage: entry}  # reassign so SQLAlchemy sees the JSONB change


def run_sync(
    job_id: int,
    session_factory: Callable[[], Session],
    client_factory: Callable[[], GitHubClient],
    limits: Optional[Limits] = None,
) -> None:
    db = session_factory()
    gh = client_factory()
    try:
        job = db.get(SyncJob, job_id)
        if job is None:
            return
        repo = db.get(Repository, job.repository_id)
        started = utcnow()
        job.status, job.started_at, job.errors = "running", started, []
        job.progress = {s: {"status": "pending"} for s in STAGES}
        db.commit()

        sync = Sync(db, gh, repo, job, limits or Limits.for_token(gh.has_token))
        new_cursors: Dict[str, str] = {}
        errors: List[Dict[str, Any]] = []
        failed = False
        for i, stage in enumerate(STAGES):
            job.stage = stage
            _set(job, stage, {"status": "running"})
            db.commit()
            try:
                result = getattr(sync, stage)()
                status = "skipped" if "skipped" in result else "done"
                _set(job, stage, {"status": status, **result})
                if status == "done":
                    new_cursors[stage] = iso(started - CURSOR_SKEW)
                db.commit()
            except Exception as exc:  # record, keep the data already committed, move on
                db.rollback()
                expected = isinstance(exc, GitHubError)
                if not expected:
                    log.exception("sync %s stage %s crashed", job_id, stage)
                message = str(exc) if expected else f"Internal error ({exc.__class__.__name__})."
                errors.append({"stage": stage, "error": exc.__class__.__name__, "message": message})
                _set(job, stage, {"status": "failed", "message": message})
                if stage == "metadata" or isinstance(exc, RateLimited):
                    # Without metadata nothing else is meaningful; after a rate limit every request would fail.
                    for rest in STAGES[i + 1 :]:
                        _set(job, rest, {"status": "skipped", "message": "Stopped after an earlier failure."})
                    failed = stage == "metadata"
                    job.errors = errors
                    db.commit()
                    break
                job.errors = errors
                db.commit()

        job.finished_at = utcnow()
        job.status = "failed" if failed else ("partial" if errors else "completed")
        job.stage = "failed" if failed else "done"
        job.errors = errors
        job.progress = {**job.progress, "github_requests": gh.requests_made, "rate_limit": dict(gh.rate_limit)}
        if not failed:
            repo.sync_cursors = {**(repo.sync_cursors or {}), **new_cursors}
            repo.last_synced_at = started
        db.commit()
    except Exception:  # the job record itself could not be updated
        log.exception("sync job %s aborted", job_id)
        db.rollback()
        job = db.get(SyncJob, job_id)
        if job is not None:
            job.status, job.stage, job.finished_at = "failed", "failed", utcnow()
            job.errors = (job.errors or []) + [{"stage": job.stage, "error": "Aborted", "message": "Sync aborted unexpectedly."}]
            db.commit()
    finally:
        gh.close()
        db.close()


def start_job(db: Session, repo: Repository, full: bool = False) -> tuple[SyncJob, bool]:
    """Return (job, created). An already queued or running job is reused, never duplicated."""
    active = db.scalars(
        select(SyncJob).where(SyncJob.repository_id == repo.id, SyncJob.status.in_(ACTIVE)).order_by(SyncJob.id.desc())
    ).first()
    if active:
        return active, False
    job = SyncJob(repository_id=repo.id, status="queued", stage="queued", full=full,
                  progress={s: {"status": "pending"} for s in STAGES}, errors=[])
    db.add(job)
    db.commit()
    db.refresh(job)
    return job, True


def fail_interrupted_jobs(db: Session) -> int:
    """Jobs left queued/running by a server restart can never finish; mark them so a retry is possible."""
    jobs = list(db.scalars(select(SyncJob).where(SyncJob.status.in_(ACTIVE))))
    for job in jobs:
        job.status, job.stage, job.finished_at = "failed", "failed", utcnow()
        job.errors = (job.errors or []) + [{"stage": "server", "error": "Interrupted",
                                            "message": "The server restarted during this sync. Start it again."}]
    db.commit()
    return len(jobs)
