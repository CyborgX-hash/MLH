"""Cross-source linking, decision deduplication and decision-to-code mapping (PostgreSQL)."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.deps import get_db
from app.main import app
from app.models import (
    Comment, Commit, Decision, DecisionEvent, Discussion, Issue, PullRequest, PullRequestFile, Repository, SourceFile,
    SourceLink,
)
from app.schemas.extraction import CandidateDecision
from app.services.evidence.records import create_decision
from app.services.impact.code_map import NO_EVIDENCE, map_decision
from app.services.linking.detector import rebuild_links
from app.services.linking.refs import find_refs

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
URL = "https://github.com/acme/shop"


def at(days):
    return T0 + timedelta(days=days)


class World:
    def __init__(self, db):
        self.db = db
        self.repo = Repository(github_id=1, node_id="R1", owner="acme", name="shop", full_name="acme/shop",
                               html_url=URL, default_branch="main", sync_cursors={})
        db.add(self.repo)
        db.flush()
        self.n = 0

    def issue(self, number, title, body=""):
        i = Issue(repository_id=self.repo.id, github_id=number, node_id=f"I{number}", number=number, title=title,
                  body=body, state="open", html_url=f"{URL}/issues/{number}", author_login="alice")
        self.db.add(i)
        self.db.flush()
        return i

    def discussion(self, number, title, body=""):
        d = Discussion(repository_id=self.repo.id, node_id=f"D{number}", number=number, title=title, body=body,
                       html_url=f"{URL}/discussions/{number}")
        self.db.add(d)
        self.db.flush()
        return d

    def pr(self, number, title, body="", merged=None, sha=None, files=()):
        p = PullRequest(repository_id=self.repo.id, github_id=number, node_id=f"P{number}", number=number, title=title,
                        body=body, state="closed", html_url=f"{URL}/pull/{number}", gh_merged_at=merged,
                        merge_commit_sha=sha, author_login="carol")
        self.db.add(p)
        self.db.flush()
        for f in files:
            name, status, prev = (f + (None,))[:3]
            self.db.add(PullRequestFile(pull_request_id=p.id, filename=name, status=status, previous_filename=prev))
        self.db.flush()
        return p

    def commit(self, sha, message, when=None):
        c = Commit(repository_id=self.repo.id, sha=sha, message=message, html_url=f"{URL}/commit/{sha}",
                   committed_at=when, author_login="carol")
        self.db.add(c)
        self.db.flush()
        return c

    def comment(self, parent_kind, parent_number, body, login="dave", assoc="OWNER"):
        self.n += 1
        c = Comment(repository_id=self.repo.id, node_id=f"C{self.n}", kind="issue_comment", parent_kind=parent_kind,
                    parent_number=parent_number, author_login=login, author_association=assoc, body=body,
                    html_url=f"{URL}/issues/{parent_number}#issuecomment-{self.n}")
        self.db.add(c)
        self.db.flush()
        return f"comment:{c.id}"


S25, S99 = "a" * 40, "b" * 40


@pytest.fixture
def w(db):
    w = World(db)
    w.i12 = w.issue(12, "Choose a database for orders", "MongoDB proposed for order storage. Code lives in `src/db.py`.")
    w.d8 = w.discussion(8, "MongoDB versus PostgreSQL", "Continuing #12. PostgreSQL has real transactions.")
    w.p20 = w.pr(20, "Mongo prototype", "Prototype only.")
    w.p25 = w.pr(25, "Implement PostgreSQL storage", "Closes #12. Supersedes #20.", merged=at(10), sha=S25, files=[
        ("src/db.py", "modified"), ("src/models.py", "added"), ("src/api.py", "modified"), ("src/legacy_mongo.py", "removed")])
    w.p30 = w.pr(30, "Restructure storage package", "", merged=at(20), files=[("storage/db.py", "renamed", "src/db.py")])
    w.p31 = w.pr(31, "Drop ORM models", "", merged=at(30), files=[("src/models.py", "removed")])
    w.p32 = w.pr(32, "Add pagination", "", merged=at(40), files=[("src/api.py", "modified")])
    w.p33 = w.pr(33, "Old change", "", merged=at(5), files=[("src/api.py", "modified")])  # before #25: not "after"
    w.i40 = w.issue(40, "PostgreSQL pooling for orders storage", "Tune PostgreSQL pooling for orders storage transactions.")
    w.i50 = w.issue(50, "Logo colour", "Use colour #000000 and see other/repo#25 and #999. ```see #12```")
    w.c25 = w.commit(S25, "Implement PostgreSQL storage (#25)", at(10))
    w.c99 = w.commit(S99, f"Revert storage\n\nThis reverts commit {S25}.", at(11))
    w.ev_maint = w.comment("issue", 12, "We decided to use PostgreSQL for orders because we need transactions.")
    w.ev_d8 = w.comment("discussion", 8, "PostgreSQL for orders, agreed: transactions matter.", login="dave")
    w.ev_40 = w.comment("issue", 40, "PostgreSQL pooling settings for orders storage.", login="erin", assoc="NONE")
    w.ev_50 = w.comment("issue", 50, "Use a dark colour for the logo.", login="erin", assoc="NONE")
    w.ev_20 = w.comment("pull_request", 20, "Mongo prototype for the orders store.", login="erin", assoc="NONE")
    db.add(SourceFile(repository_id=w.repo.id, path="src/other.py", blob_sha="c" * 40, size=10, priority=3,
                      content="# PostgreSQL logo colour helpers", html_url=f"{URL}/blob/main/src/other.py"))
    db.commit()
    rebuild_links(db, w.repo)
    db.commit()
    return w


def links(db, **where):
    q = select(SourceLink)
    for k, v in where.items():
        q = q.where(getattr(SourceLink, k) == v)
    return list(db.scalars(q))


def one(db, src, tgt, **where):
    return links(db, source_kind=src[0], source_id=src[1], target_kind=tgt[0], target_id=tgt[1], **where)


def key(rec):
    kind = {"Issue": "issue", "PullRequest": "pull_request", "Discussion": "discussion", "Commit": "commit"}[type(rec).__name__]
    return kind, rec.id


# ---------------------------------------------------------------- Prompt 10: linking

def test_reference_parser_ignores_other_repos_code_and_unknown_shapes():
    refs = find_refs("Fixes #3, see acme/shop#4, other/repo#5, `#6`, https://github.com/acme/shop/pull/7, color #fff",
                     "acme", "shop")
    assert {(r.number, r.relation) for r in refs} == {(3, "implements"), (4, "references"), (7, "references")}
    by = find_refs("This was superseded by #9", "acme", "shop")
    assert by[0].relation == "supersedes" and by[0].reverse


def test_discussion_reference_is_verified_discusses_with_evidence(db, w):
    [l] = one(db, key(w.d8), key(w.i12))
    assert (l.relation, l.verification_status, l.signal) == ("discusses", "verified", "explicit_reference")
    assert "Continuing #12" in l.evidence["snippet"] and l.evidence["url"].endswith("/discussions/8")


def test_closing_keyword_means_implements(db, w):
    [l] = one(db, key(w.p25), key(w.i12))
    assert (l.relation, l.signal, l.verification_status) == ("implements", "closing_keyword", "verified")


def test_supersedes_and_revert_relations(db, w):
    assert one(db, key(w.p25), key(w.p20))[0].relation == "supersedes"
    [revert] = one(db, key(w.c99), key(w.c25))
    assert revert.relation == "conflicts_with" and revert.verification_status == "verified"


def test_commit_links_to_pr_by_message_and_merge_metadata(db, w):
    signals = {l.signal for l in one(db, key(w.c25), key(w.p25))}
    assert signals == {"commit_reference", "linked_pr_metadata"}


def test_no_links_from_other_repos_unknown_numbers_or_code(db, w):
    assert links(db, source_kind="issue", source_id=w.i50.id, verification_status="verified") == []


def test_similarity_and_shared_files_are_only_possible(db, w):
    possible = links(db, verification_status="possible")
    assert possible and all(l.relation == "related_to" for l in possible)
    assert {l.signal for l in possible} <= {"shared_files", "terminology", "semantic_similarity"}
    assert any({("issue", w.i40.id)} & {(l.source_kind, l.source_id), (l.target_kind, l.target_id)} for l in possible)
    # issue #12 already has a verified link to PR #25, so no extra "possible" duplicate
    assert not one(db, key(w.i12), key(w.p25), verification_status="possible")


def test_rebuild_is_idempotent(db, w):
    before = sorted((l.source_kind, l.source_id, l.target_kind, l.target_id, l.relation, l.signal) for l in links(db))
    rebuild_links(db, w.repo)
    db.commit()
    after = sorted((l.source_kind, l.source_id, l.target_kind, l.target_id, l.relation, l.signal) for l in links(db))
    assert before == after


# ---------------------------------------------------------------- deduplication

def cand(topic, *source_ids, decision="Use PostgreSQL", status="accepted"):
    return CandidateDecision.model_validate({
        "topic": topic, "decision": decision, "decision_status": status,
        "resolution_evidence": [{"source_id": s, "quote": None} for s in source_ids],
    })


def test_same_decision_from_linked_discussion_is_merged_not_duplicated(db, w):
    a, _ = create_decision(db, w.repo, cand("Database for orders", w.ev_maint))
    b, result = create_decision(db, w.repo, cand("Database for orders storage", w.ev_d8))
    assert b.id == a.id and result.merged_into == a.id
    assert db.scalar(select(func.count()).select_from(Decision)) == 1
    events = [e.event for e in db.scalars(select(DecisionEvent).where(DecisionEvent.decision_id == a.id))]
    assert events == ["created", "merged_duplicate"]


def test_possible_links_never_merge_decisions(db, w):
    a, _ = create_decision(db, w.repo, cand("Database for orders", w.ev_maint))
    c, result = create_decision(db, w.repo, cand("Database for orders", w.ev_40))
    assert c.id != a.id and result.merged_into is None


def test_linked_but_different_topic_is_a_new_decision(db, w):
    a, _ = create_decision(db, w.repo, cand("Database for orders", w.ev_maint))
    c, _ = create_decision(db, w.repo, cand("Continuous integration provider", w.ev_d8, decision="Use GitHub Actions"))
    assert c.id != a.id


def test_merge_with_different_outcome_requests_review(db, w):
    a, _ = create_decision(db, w.repo, cand("Database for orders", w.ev_maint))
    merged, _ = create_decision(db, w.repo, cand("Database for orders", w.ev_d8, decision="Use MongoDB"))
    assert merged.id == a.id and merged.requires_human_review and merged.decision == "Use PostgreSQL"


# ---------------------------------------------------------------- Prompt 11: code mapping

def test_decision_to_code_mapping_follows_renames_deletions_and_later_changes(db, w):
    d, _ = create_decision(db, w.repo, cand("Database for orders", w.ev_maint))
    result = map_decision(db, d)
    assert result["message"] is None
    files = {r.path: r for r in result["verified"]}
    assert set(files) == {"src/db.py", "src/models.py", "src/api.py", "src/legacy_mongo.py"}
    assert all(r.pr_number == 25 and r.pr_url == f"{URL}/pull/25" for r in files.values())
    assert files["src/db.py"].commit_url == f"{URL}/commit/{S25}" and "closing keyword" in files["src/db.py"].basis
    assert (files["src/db.py"].current_path, files["src/db.py"].changed_after) == ("storage/db.py", [30])
    assert files["src/models.py"].deleted and files["src/models.py"].current_path is None
    assert files["src/api.py"].changed_after == [32]  # PR #33 merged before #25 does not count
    assert files["src/legacy_mongo.py"].deleted and files["src/legacy_mongo.py"].change_type == "removed"


def test_one_pr_can_implement_several_decisions(db, w):
    a, _ = create_decision(db, w.repo, cand("Database for orders", w.ev_maint))
    b, _ = create_decision(db, w.repo, cand("Remove the Mongo prototype code", w.ev_maint, decision="Delete legacy Mongo layer"))
    assert a.id != b.id
    assert {r.pr_number for r in map_decision(db, a)["verified"]} == {25}
    assert {r.pr_number for r in map_decision(db, b)["verified"]} == {25}


def test_unmerged_pr_is_not_an_implementation(db, w):
    d, _ = create_decision(db, w.repo, cand("Mongo prototype for orders store", w.ev_20, decision="Use MongoDB"))
    result = map_decision(db, d)
    assert result["message"] == NO_EVIDENCE and any("never merged" in n for n in result["notes"])


def test_never_implemented_decision_says_so_even_with_possible_mappings(db, w):
    d, _ = create_decision(db, w.repo, cand("PostgreSQL pooling for orders storage", w.ev_40, decision="Tune pooling"))
    result = map_decision(db, d)
    assert result["verified"] == [] and result["message"] == NO_EVIDENCE


def test_keyword_in_file_content_is_not_implementation_evidence(db, w):
    d, _ = create_decision(db, w.repo, cand("Logo colour", w.ev_50, decision="Use PostgreSQL logo colour"))
    result = map_decision(db, d)
    assert result["verified"] == [] and result["possible"] == [] and result["message"] == NO_EVIDENCE


def test_api_related_graph_code_map_and_file_lookup(session_factory, db, w):
    d, _ = create_decision(db, w.repo, cand("Database for orders", w.ev_maint))

    def db_override():
        with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = db_override
    try:
        api = TestClient(app)
        graph = api.get(f"/api/decisions/{d.id}/related").json()
        cited = [r for r in graph["records"] if r["cited"]]
        assert [(r["kind"], r["number"]) for r in cited] == [("issue", 12)]
        rels = {(l["relation"], l["verification_status"]) for l in graph["links"]}
        assert ("implements", "verified") in rels and ("discusses", "verified") in rels

        code = api.get(f"/api/decisions/{d.id}/code").json()
        assert code["message"] is None and len(code["verified"]) == 4
        assert {p["pr_number"] for p in code["possible"]} == {30}  # shares src/db.py with issue #12: possible only

        for path in ("storage/db.py", "src/db.py"):
            hits = api.get(f"/api/repositories/{w.repo.id}/files/decisions", params={"path": path}).json()
            assert [h["decision_id"] for h in hits] == [d.id]
        assert api.get(f"/api/repositories/{w.repo.id}/files/decisions", params={"path": "README.md"}).json() == []

        assert api.post(f"/api/repositories/{w.repo.id}/links/rebuild").json()["verified"] >= 5
        assert api.get(f"/api/repositories/{w.repo.id}/links", params={"verification_status": "possible"}).status_code == 200
    finally:
        app.dependency_overrides.clear()
