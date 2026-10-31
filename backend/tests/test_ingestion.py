"""Integration tests: the full ingestion workflow against PostgreSQL with a mocked GitHub."""
import httpx
from sqlalchemy import func, select

from app.db.upsert import upsert
from app.models import Comment, Commit, Discussion, Issue, PullRequest, PullRequestFile, Repository, SourceFile, SyncJob
from app.workers.ingestion import Limits, fail_interrupted_jobs, repository_fields, run_sync, start_job
from tests.github_fake import O, R, FakeGitHub

LIMITS = Limits(issues=50, issue_comments=50, pull_requests=50, pr_details=50, review_comments=50,
                discussions=10, commits=50, files=10)


def connect(db, fake):
    upsert(db, Repository, [{**repository_fields(fake.repo), "sync_cursors": {}}], ["github_id"])
    db.commit()
    return db.scalars(select(Repository)).one()


def sync(session_factory, db, fake, repo, full=False, token="t"):
    job, _ = start_job(db, repo, full=full)
    run_sync(job.id, session_factory, lambda: fake.client(token=token), LIMITS)
    db.expire_all()
    return db.get(SyncJob, job.id)


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_full_sync_stores_everything_with_urls_authors_and_timestamps(session_factory, db):
    fake = FakeGitHub()
    repo = connect(db, fake)
    job = sync(session_factory, db, fake, repo)

    assert job.status == "completed" and job.stage == "done" and job.errors == []
    assert all(job.progress[s]["status"] == "done" for s in ("issues", "pull_requests", "discussions", "code"))

    issues = db.scalars(select(Issue).order_by(Issue.number)).all()
    assert [i.number for i in issues] == [1, 3]  # PR #2 is not stored as an issue
    assert issues[0].html_url.endswith("/issues/1") and issues[0].author_login == "alice"
    assert issues[0].gh_created_at is not None

    pr = db.scalars(select(PullRequest)).one()
    assert pr.number == 2 and pr.gh_merged_at is not None and pr.details_updated_at == pr.gh_updated_at
    f = db.scalars(select(PullRequestFile)).one()
    assert (f.filename, f.previous_filename, f.status) == ("src/db.py", "src/database.py", "renamed")

    kinds = {c.kind: c for c in db.scalars(select(Comment))}
    assert set(kinds) == {"issue_comment", "review", "review_comment", "discussion_comment", "discussion_reply"}
    assert kinds["review"].review_state == "APPROVED"
    assert kinds["review_comment"].path == "src/db.py"
    assert kinds["discussion_reply"].in_reply_to == "DC_1"
    pr_conv = db.scalars(select(Comment).where(Comment.node_id == "IC_12")).one()
    assert (pr_conv.parent_kind, pr_conv.parent_number) == ("pull_request", 2)

    assert count(db, Discussion) == 1
    assert db.scalars(select(Commit)).one().author_login == "carol"
    files = {s.path: s for s in db.scalars(select(SourceFile))}
    assert set(files) == {"README.md", "docs/adr/0001-database.md", "src/db.py"}
    assert files["docs/adr/0001-database.md"].priority == 0 and "PostgreSQL" in files["docs/adr/0001-database.md"].content

    db.refresh(repo)
    assert repo.last_synced_at is not None and set(repo.sync_cursors) >= {"issues", "pull_requests", "commits", "code"}


def test_resync_upserts_without_duplicates_and_skips_unchanged_data(session_factory, db):
    fake = FakeGitHub()
    repo = connect(db, fake)
    sync(session_factory, db, fake, repo)
    totals = [count(db, m) for m in (Issue, PullRequest, Comment, Commit, SourceFile, PullRequestFile)]
    reviews_before = fake.count(f"/repos/{O}/{R}/pulls/2/reviews")
    contents_before = fake.count(f"/repos/{O}/{R}/contents/")

    job = sync(session_factory, db, fake, repo, full=True)  # same data again, ignoring cursors

    assert [count(db, m) for m in (Issue, PullRequest, Comment, Commit, SourceFile, PullRequestFile)] == totals
    assert fake.count(f"/repos/{O}/{R}/pulls/2/reviews") == reviews_before  # PR unchanged: details skipped
    assert fake.count(f"/repos/{O}/{R}/contents/") == contents_before  # same blob SHAs: no re-download
    assert job.progress["pull_requests"]["details_unchanged"] == 1
    assert job.progress["code"]["unchanged"] == 3


def test_incremental_sync_sends_since_cursor(session_factory, db):
    fake = FakeGitHub()
    repo = connect(db, fake)
    sync(session_factory, db, fake, repo)
    fake.queries.clear()
    sync(session_factory, db, fake, repo)
    assert any("since" in q for q in fake.queries)  # issues, comments, commits use the saved cursor


def test_updated_pr_refetches_details_and_file_changes(session_factory, db):
    fake = FakeGitHub()
    repo = connect(db, fake)
    sync(session_factory, db, fake, repo)
    fake.pulls = [dict(fake.pulls[0], updated_at="2026-10-20T00:00:00Z")]
    fake.files[2] = [{"filename": "src/other.py", "status": "added", "additions": 1, "deletions": 0, "sha": "9" * 40}]
    sync(session_factory, db, fake, repo, full=True)
    assert [f.filename for f in db.scalars(select(PullRequestFile))] == ["src/other.py"]


def test_failed_stage_gives_partial_job_and_keeps_other_data(session_factory, db):
    fake = FakeGitHub()
    fake.fail[f"/repos/{O}/{R}/commits"] = lambda: httpx.Response(500)
    repo = connect(db, fake)
    job = sync(session_factory, db, fake, repo)
    assert job.status == "partial"
    assert job.progress["commits"]["status"] == "failed"
    assert job.progress["code"]["status"] == "done"  # later stages still ran
    assert job.errors[0]["stage"] == "commits" and job.errors[0]["error"] == "Unavailable"
    assert count(db, Issue) == 2 and count(db, Commit) == 0
    db.refresh(repo)
    assert "commits" not in repo.sync_cursors  # failed stage will be fully retried next time


def test_rate_limit_skips_github_stages_but_still_links_and_indexes(session_factory, db):
    fake = FakeGitHub()
    fake.fail[f"/repos/{O}/{R}/pulls"] = lambda: httpx.Response(
        403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "9999999999"}, json={})
    repo = connect(db, fake)
    job = sync(session_factory, db, fake, repo)
    assert job.status == "partial"
    assert job.progress["pull_requests"]["status"] == "failed"
    assert job.progress["code"]["status"] == "skipped" and "rate limit" in job.progress["code"]["message"]
    assert job.progress["links"]["status"] == "done" and job.progress["index"]["status"] == "done"
    assert "rate limit" in job.errors[0]["message"] and len(job.errors) == 1
    assert fake.count(f"/repos/{O}/{R}/commits") == 0  # no GitHub calls after the limit


def test_metadata_failure_fails_job(session_factory, db):
    fake = FakeGitHub()
    repo = connect(db, fake)
    fake.fail[f"/repos/{O}/{R}"] = lambda: httpx.Response(404, json={})
    job = sync(session_factory, db, fake, repo)
    assert job.status == "failed" and job.stage == "failed"
    db.refresh(repo)
    assert repo.last_synced_at is None


def test_discussions_skipped_without_token_or_when_disabled(session_factory, db):
    fake = FakeGitHub()
    repo = connect(db, fake)
    job = sync(session_factory, db, fake, repo, token=None)
    assert job.status == "completed"
    assert "GITHUB_TOKEN" in job.progress["discussions"]["skipped"]
    assert fake.count("/graphql") == 0

    fake.repo["has_discussions"] = False
    job = sync(session_factory, db, fake, repo)
    assert "not enabled" in job.progress["discussions"]["skipped"]


def test_only_one_active_job_and_interrupted_jobs_are_failed(db):
    fake = FakeGitHub()
    repo = connect(db, fake)
    job1, created1 = start_job(db, repo)
    job2, created2 = start_job(db, repo)
    assert created1 and not created2 and job1.id == job2.id
    assert fail_interrupted_jobs(db) == 1
    db.refresh(job1)
    assert job1.status == "failed" and job1.errors[-1]["error"] == "Interrupted"
