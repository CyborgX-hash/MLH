"""PR impact analysis against historical decisions (PostgreSQL + mocked GitHub PR API)."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db, get_github_client
from app.main import app
from app.services.evidence.authority import Reviewer
from app.services.evidence.records import create_decision, review_decision, supersede_decision
from app.services.github.client import GitHubClient
from app.services.github.errors import InvalidRepositoryURL
from app.services.github.urls import parse_pr_url
from app.services.impact.pr_impact import NOTE, diff_lines, key_terms
from tests.test_rag import cand
from tests.test_rag import w  # noqa: F401  (fixture)

PATCH_CONFLICT = """@@ -1,4 +1,3 @@
-with conn.transaction():
-    save(order)
+save(order)
+client = MongoDB(url)
"""
PATCH_HARMLESS = """@@ -1,2 +1,3 @@
 with conn.transaction():
+    log.info("saving order")
     save(order)
"""


def fake_github(files, number=99, merged=False):
    def handler(req: httpx.Request):
        path = req.url.path
        if path == f"/repos/acme/shop/pulls/{number}":
            return httpx.Response(200, json={"number": number, "title": "Refactor order saving", "state": "open",
                                             "html_url": f"https://github.com/acme/shop/pull/{number}",
                                             "merged_at": "2026-10-01T00:00:00Z" if merged else None, "user": {"login": "zoe"}})
        if path == f"/repos/acme/shop/pulls/{number}/files":
            return httpx.Response(200, json=files)
        return httpx.Response(404, json={"message": "Not Found"})
    return GitHubClient(transport=httpx.MockTransport(handler), sleep=lambda s: None)


@pytest.fixture
def api(session_factory):
    def db_override():
        with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = db_override
    yield TestClient(app)
    app.dependency_overrides.clear()


def run(api, files, url="https://github.com/acme/shop/pull/99"):
    app.dependency_overrides[get_github_client] = lambda: fake_github(files)
    return api.post("/api/pr-impact", json={"pr_url": url})


def test_parse_pr_url():
    assert parse_pr_url("https://github.com/psf/requests/pull/7272/files") == ("psf", "requests", 7272)
    for bad in ("https://github.com/psf/requests", "https://github.com/psf/requests/issues/3", "https://gitlab.com/a/b/pull/1"):
        with pytest.raises(InvalidRepositoryURL):
            parse_pr_url(bad)


def test_terms_and_diff_helpers():
    assert key_terms("Use PostgreSQL transactions") == {"postgresql", "transaction"}
    assert diff_lines(PATCH_CONFLICT) == (["save(order)", "client = MongoDB(url)"], ["with conn.transaction():", "save(order)"])


def test_potential_conflict_explains_decision_reason_source_and_files(api, w):
    r = run(api, [{"filename": "src/db.py", "status": "modified", "additions": 2, "deletions": 2, "patch": PATCH_CONFLICT}])
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["note"] == NOTE and "never blocks" in rep["note"]
    [f] = [f for f in rep["findings"] if f["decision_id"] == w.pg_decision.id]
    assert f["severity"] == "potential_conflict" and f["headline"] == "Potential conflict with historical decision"
    signals = {t["signal"] for t in f["triggers"]}
    assert signals == {"removes_decision_code", "introduces_rejected"}
    removed = next(t for t in f["triggers"] if t["signal"] == "removes_decision_code")
    assert "transaction" in removed["detail"] and removed["lines"] == ["with conn.transaction():"]
    assert "PR #25" in removed["detail"]
    rejected = next(t for t in f["triggers"] if t["signal"] == "introduces_rejected")
    assert "MongoDB" in rejected["detail"] and "reason not recorded" in rejected["detail"]
    assert f["triggered_by_files"] == ["src/db.py"]
    assert f["supporting_sources"] and all(s["url"].startswith("https://github.com/acme/shop/") for s in f["supporting_sources"])
    assert "block" not in r.text.replace("never blocks", "")  # nothing gates the PR


def test_harmless_change_to_implementing_file_is_only_related(api, w):
    rep = run(api, [{"filename": "src/db.py", "status": "modified", "patch": PATCH_HARMLESS}]).json()
    [f] = rep["findings"]
    assert f["severity"] == "related" and f["triggers"][0]["signal"] == "touches_implementation"


def test_deleting_implementing_file(api, w):
    rep = run(api, [{"filename": "src/db.py", "status": "removed", "patch": None}]).json()
    assert rep["findings"][0]["triggers"][0]["signal"] == "deletes_implementation"


def test_renamed_file_is_matched_by_previous_name(api, w):
    rep = run(api, [{"filename": "storage/db.py", "previous_filename": "src/db.py", "status": "renamed", "patch": PATCH_HARMLESS}]).json()
    assert [f["decision_id"] for f in rep["findings"]] == [w.pg_decision.id]


def test_unrelated_pr_has_no_findings(api, w):
    rep = run(api, [{"filename": "docs/index.md", "status": "modified", "patch": "+Typo fix"}]).json()
    assert rep["findings"] == [] and rep["decisions_checked"] == 2


def test_unresolved_decision_never_produces_a_conflict(api, w, db):
    # The queue decision (Kafka vs RabbitMQ) is unresolved: adding either one is not a conflict with anything.
    rep = run(api, [{"filename": "src/events.py", "status": "added", "patch": "+producer = Kafka(brokers)\n+q = RabbitMQ()"}]).json()
    assert rep["findings"] == []


def test_human_rejection_counts_and_superseded_decisions_are_ignored(api, w, db):
    review_decision(db, w.queue_decision, Reviewer("dave", "maintain"), "accepted", "Chosen in the architecture call.",
                    selected_alternative="Kafka", rejected=[{"name": "RabbitMQ", "reason": "No replay"}])
    rep = run(api, [{"filename": "src/events.py", "status": "added", "patch": "+q = RabbitMQ()"}]).json()
    [f] = rep["findings"]
    assert f["decision_id"] == w.queue_decision.id and "No replay" in f["triggers"][0]["detail"]

    newer, _ = create_decision(db, w.repo, cand("Event streaming platform", w.kafka, decision="Use Kafka", status="accepted"))
    supersede_decision(db, w.queue_decision, newer, Reviewer("dave", "maintain"), "Replaced by the streaming platform decision.")
    assert run(api, [{"filename": "src/events.py", "status": "added", "patch": "+q = RabbitMQ()"}]).json()["findings"] == []


def test_errors(api, w):
    assert run(api, [], url="https://github.com/acme/shop/issues/3").status_code == 422
    r = run(api, [], url="https://github.com/other/repo/pull/1")
    assert r.status_code == 404 and "not connected" in r.json()["detail"]
    r = run(api, [], url="https://github.com/acme/shop/pull/12345")
    assert r.status_code == 404 and "#12345 was not found" in r.json()["detail"]
