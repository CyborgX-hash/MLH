"""Real GitHub totals, how a sync ran, and plain-language decision lists."""
import json

import httpx
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.models import SyncJob
from app.services.github.client import GitHubClient
from app.services.history.views import overview
from tests.test_rag import w  # noqa: F401  (fixture)


def test_totals_with_token_come_from_one_graphql_query():
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append(body["query"])
        return httpx.Response(200, json={"data": {"repository": {
            "openIssues": {"totalCount": 1401}, "closedIssues": {"totalCount": 2873},
            "openPRs": {"totalCount": 1312}, "mergedPRs": {"totalCount": 4100}, "closedPRs": {"totalCount": 900},
            "discussions": {"totalCount": 57}, "hasDiscussionsEnabled": True, "stargazerCount": 10100, "forkCount": 2500,
            "defaultBranchRef": {"target": {"history": {"totalCount": 6575}}}}}})

    s = GitHubClient(token="t", transport=httpx.MockTransport(handler)).get_repository_stats("sktime", "sktime")
    assert len(seen) == 1 and "openIssues" in seen[0]
    assert s == {"open_issues": 1401, "closed_issues": 2873, "open_prs": 1312, "merged_prs": 4100, "closed_prs": 900,
                 "commits": 6575, "discussions": 57, "discussions_enabled": True, "stars": 10100, "forks": 2500,
                 "source": "graphql"}


def test_totals_without_token_use_rest_search_and_commit_pages():
    def handler(req: httpx.Request):
        path, q = req.url.path, req.url.params.get("q", "")
        if path == "/search/issues":
            return httpx.Response(200, json={"total_count": {
                "is:issue is:open": 10, "is:issue is:closed": 20, "is:pr is:open": 3, "is:pr is:merged": 40,
                "is:pr is:closed is:unmerged": 5}[q.split(" ", 1)[1]]})
        if path.endswith("/commits"):
            last = "https://api.github.com/repos/o/r/commits?per_page=1&page=6575"
            return httpx.Response(200, json=[{}], headers={"link": f'<{last}>; rel="last"'})
        return httpx.Response(200, json={"has_discussions": True, "stargazers_count": 7, "forks_count": 1})

    s = GitHubClient(transport=httpx.MockTransport(handler)).get_repository_stats("o", "r")
    assert (s["open_issues"], s["closed_issues"], s["open_prs"], s["merged_prs"], s["closed_prs"]) == (10, 20, 3, 40, 5)
    assert s["commits"] == 6575 and s["discussions"] is None and s["discussions_enabled"] and s["source"] == "rest"


def test_overview_reports_unauthenticated_sync_and_top_threads(db, w):
    db.add(SyncJob(repository_id=w.repo.id, status="completed", stage="done", full=False,
                   progress={"rate_limit": {"limit": 60, "remaining": 3}}, errors=[]))
    db.commit()
    o = overview(db, w.repo)
    assert o["sync"]["authenticated"] is False and o["sync"]["limits"]["issues"] == 100
    top = o["top_threads"]
    assert top[0]["number"] == 12 and top[0]["comments"] == 2 and top[0]["analysed"] is False
    assert top[0]["url"].endswith("/issues/12")


def test_decision_list_names_threads_people_and_exact_quotes(session_factory, db, w):
    def db_override():
        with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = db_override
    try:
        items = {i["id"]: i for i in TestClient(app).get(f"/api/repositories/{w.repo.id}/decisions").json()}
    finally:
        app.dependency_overrides.clear()
    pg = items[w.pg_decision.id]
    assert {(s["kind"], s["number"]) for s in pg["sources"]} == {("issue", 12)}
    assert pg["sources"][0]["url"].endswith("/issues/12") and pg["sources"][0]["title"]
    assert {p["login"] for p in pg["participants"]} == {"dave"}
    assert 0 < pg["verified_evidence"] <= pg["evidence_count"]
    queue = items[w.queue_decision.id]
    assert {p["login"] for p in queue["participants"]} == {"ann", "ben"}


def test_sync_stores_github_totals_and_survives_their_failure(session_factory, db):
    from tests.test_ingestion import LIMITS, connect, sync
    from tests.github_fake import FakeGitHub
    fake = FakeGitHub()
    repo = connect(db, fake)
    job = sync(session_factory, db, fake, repo)
    db.refresh(repo)
    assert job.status == "completed"
    assert (repo.stats["open_issues"], repo.stats["commits"], repo.stats["discussions"]) == (2, 42, 1)

    fake.fail["/graphql"] = lambda: httpx.Response(502)  # totals unavailable: sync must still complete
    job = sync(session_factory, db, fake, repo, full=True)
    assert job.progress["metadata"]["status"] == "done"
    db.refresh(repo)
    assert repo.stats["commits"] == 42  # previous totals kept
    assert LIMITS


def test_top_threads_include_busy_threads_whose_record_was_not_collected(db, w):
    from app.models import Comment
    for i in range(3):
        db.add(Comment(repository_id=w.repo.id, node_id=f"OLD{i}", kind="issue_comment", parent_kind="pull_request",
                       parent_number=6787, author_login="x", body="old", html_url=f"{w.repo.html_url}/pull/6787#c{i}"))
    db.commit()
    top = overview(db, w.repo)["top_threads"]
    assert (top[0]["number"], top[0]["title"], top[0]["url"]) == (6787, None, f"{w.repo.html_url}/pull/6787")
