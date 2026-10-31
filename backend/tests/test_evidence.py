"""Evidence validation, status rules, conflicts and human review (PostgreSQL + mocked reviewer identity)."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.deps import get_db
from tests.conftest import ADMIN
from app.api.routes.decisions import get_reviewer_verifier
from app.main import app
from app.models import Comment, Decision, DecisionEvidence, PullRequest, Repository
from app.schemas.extraction import CandidateDecision
from app.services.evidence.authority import Reviewer, permission_level
from app.services.evidence.records import create_decision
from app.services.evidence.validator import validate

NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def make_repo(db, owner="acme", name="shop", gid=1):
    repo = Repository(github_id=gid, node_id=f"R{gid}", owner=owner, name=name, full_name=f"{owner}/{name}",
                      html_url=f"https://github.com/{owner}/{name}", default_branch="main", sync_cursors={})
    db.add(repo)
    db.flush()
    return repo


def comment(db, repo, n, login, assoc, body, review_state=None):
    c = Comment(repository_id=repo.id, github_id=n, node_id=f"C{repo.id}_{n}", kind="review" if review_state else "issue_comment",
                parent_kind="issue", parent_number=12, author_login=login, author_association=assoc, body=body,
                review_state=review_state, html_url=f"{repo.html_url}/issues/12#issuecomment-{n}", gh_created_at=NOW)
    db.add(c)
    db.flush()
    return f"comment:{c.id}"


@pytest.fixture
def world(db):
    repo = make_repo(db)
    other = make_repo(db, "evil", "corp", gid=2)
    ids = {
        "mongo": comment(db, repo, 1, "alice", "MEMBER", "We should use MongoDB for the order data."),
        "pg": comment(db, repo, 2, "bob", "CONTRIBUTOR",
                      "PostgreSQL would be better because we need transactions and relational constraints."),
        "later": comment(db, repo, 3, "carol", "NONE", "Let's discuss this further."),
        "maint": comment(db, repo, 4, "dave", "OWNER",
                         "We decided to go with PostgreSQL. MongoDB does not support the multi-document transactions we need."),
        "outsider": comment(db, repo, 5, "erin", "NONE", "Let's go with PostgreSQL."),
        "approve": comment(db, repo, 6, "dave", "OWNER", "Looks right.", review_state="APPROVED"),
        "mongo2": comment(db, repo, 7, "frank", "NONE", "+1 for MongoDB, schemaless is simpler."),
        "mongo3": comment(db, repo, 8, "gina", "NONE", "MongoDB please, it is easier to start with."),
        "foreign": comment(db, other, 9, "mallory", "OWNER", "We decided to use Redis."),
    }
    pr = PullRequest(repository_id=repo.id, github_id=25, node_id="PR25", number=25, title="Implement PostgreSQL storage",
                     body="Moves orders to PostgreSQL.", state="closed", author_login="carol",
                     author_association="CONTRIBUTOR", html_url=f"{repo.html_url}/pull/25", gh_merged_at=NOW)
    db.add(pr)
    db.commit()
    ids["pr"] = f"pull_request:{pr.id}"
    return repo, ids


def cand(**kw) -> CandidateDecision:
    base = {"topic": "Database architecture", "problem": "Choosing a database for order data"}
    base.update(kw)
    return CandidateDecision.model_validate(base)


def ev(source_id, quote=None, url=None):
    return {"source_id": source_id, "quote": quote, "url": url}


# ---------------------------------------------------------------- Prompt 8: evidence checks

def test_valid_explicit_decision_with_verified_evidence(db, world):
    repo, ids = world
    r = validate(db, repo, cand(
        decision="Use PostgreSQL", decision_status="accepted", is_explicit=True,
        resolution_evidence=[ev(ids["maint"], "We decided to go with PostgreSQL")],
        alternatives=[
            {"name": "PostgreSQL", "status": "selected", "evidence": [ev(ids["pg"])]},
            {"name": "MongoDB", "status": "rejected", "rejection_reason": "No multi-document transactions",
             "rejection_evidence": [ev(ids["maint"], "MongoDB does not support the multi-document transactions we need")]},
        ],
        reasoning=[{"reason": "PostgreSQL gives transactions and relational constraints", "alternative": "PostgreSQL",
                    "evidence": [ev(ids["pg"])]}],
    ))
    assert (r.status, r.determination, r.decision) == ("accepted", "explicit", "Use PostgreSQL")
    assert r.verification_state == "verified" and not r.requires_human_review
    alts = {a.name: a for a in r.alternatives}
    assert alts["PostgreSQL"].status == "selected"
    assert alts["MongoDB"].status == "rejected" and alts["MongoDB"].rejection_reason == "No multi-document transactions"
    res = r.checks[0]
    assert res.state == "verified" and res.source.author_login == "dave"
    assert res.source.html_url == "https://github.com/acme/shop/issues/12#issuecomment-4"


def test_missing_comment(db, world):
    repo, _ = world
    r = validate(db, repo, cand(reasoning=[{"reason": "x y", "evidence": [ev("comment:999999")]}]))
    assert r.checks[0].state == "unsupported" and r.checks[0].flags == ["source_not_found"]
    assert r.verification_state == "unsupported" and not r.can_create


def test_wrong_repository_is_rejected_and_not_exposed(db, world):
    repo, ids = world
    r = validate(db, repo, cand(decision="Use Redis", decision_status="accepted",
                                resolution_evidence=[ev(ids["foreign"], "We decided to use Redis.")]))
    c = r.checks[0]
    assert c.state == "unsupported" and c.flags == ["wrong_repository"] and c.source is None
    assert r.decision is None and r.status == "unresolved"


@pytest.mark.parametrize("fake_id", ["comment_101", "comment:abc", "https://github.com/acme/shop/issues/12", "issue:1; DROP TABLE"])
def test_fabricated_comment_ids(db, world, fake_id):
    repo, _ = world
    r = validate(db, repo, cand(reasoning=[{"reason": "relational constraints", "evidence": [ev(fake_id)]}]))
    assert r.checks[0].flags == ["fabricated_id"] and r.checks[0].state == "unsupported"


def test_unsupported_candidate_creates_no_record(db, world):
    repo, _ = world
    d, result = create_decision(db, repo, cand(decision="Use MySQL", decision_status="accepted",
                                               resolution_evidence=[ev("comment_101", "We chose MySQL")]))
    assert d is None and result.verification_state == "unsupported"
    assert db.scalar(select(func.count()).select_from(Decision)) == 0


def test_quote_must_exist_in_stored_comment(db, world):
    repo, ids = world
    r = validate(db, repo, cand(reasoning=[
        {"reason": "transactions", "evidence": [ev(ids["pg"], "We already benchmarked MySQL last year")]}]))
    c = r.checks[0]
    assert "quote_not_found" in c.flags and c.state == "partially_verified" and c.quote is None


def test_quote_with_no_relation_is_unsupported(db, world):
    repo, ids = world
    r = validate(db, repo, cand(reasoning=[
        {"reason": "Kubernetes autoscaling", "evidence": [ev(ids["pg"], "Kubernetes autoscaling is great")]}]))
    assert r.checks[0].state == "unsupported" and "does_not_support_claim" in r.checks[0].flags


def test_claimed_url_is_never_trusted(db, world):
    repo, ids = world
    r = validate(db, repo, cand(reasoning=[{"reason": "transactions relational constraints", "evidence": [
        ev(ids["pg"], url="https://evil.example/fake")]}]))
    c = r.checks[0]
    assert "url_mismatch" in c.flags and c.state == "partially_verified"
    assert c.source.html_url.startswith("https://github.com/acme/shop/")


def test_contradictory_comments_are_unresolved_and_both_sides_kept(db, world):
    """Prompt 9 example: MongoDB vs PostgreSQL, 'let's discuss further'. The AI leans PostgreSQL."""
    repo, ids = world
    d, r = create_decision(db, repo, cand(
        decision="Use PostgreSQL", decision_status="accepted",
        resolution_evidence=[ev(ids["pg"], "PostgreSQL would be better")],
        alternatives=[{"name": "MongoDB", "status": "rejected", "evidence": [ev(ids["mongo"])]},
                      {"name": "PostgreSQL", "status": "selected", "evidence": [ev(ids["pg"])]}],
        positions=[{"alternative": "MongoDB", "stance": "support", "evidence": ev(ids["mongo"])},
                   {"alternative": "PostgreSQL", "stance": "support", "evidence": ev(ids["pg"])},
                   {"alternative": "PostgreSQL", "stance": "neutral", "evidence": ev(ids["later"])}],
    ))
    assert r.conflict_detected and r.requires_human_review
    assert (d.decision, d.status, d.determination) == (None, "unresolved", "unresolved")
    assert d.verification_state == "needs_human_review"
    assert {a.name: a.status for a in r.alternatives} == {"MongoDB": "proposed", "PostgreSQL": "proposed"}
    positions = db.scalars(select(DecisionEvidence).where(DecisionEvidence.claim_type == "position")).all()
    assert {(p.alternative, p.author_login) for p in positions} >= {("MongoDB", "alice"), ("PostgreSQL", "bob")}


def test_majority_never_decides(db, world):
    repo, ids = world
    r = validate(db, repo, cand(
        decision="Use MongoDB", decision_status="accepted",
        resolution_evidence=[ev(ids["mongo2"])],
        positions=[{"alternative": "MongoDB", "stance": "support", "evidence": ev(ids[k])} for k in ("mongo", "mongo2", "mongo3")]
        + [{"alternative": "PostgreSQL", "stance": "support", "evidence": ev(ids["pg"])}],
    ))
    assert r.decision is None and r.status == "unresolved" and r.conflict_detected


def test_non_maintainer_saying_lets_go_with_is_not_a_decision(db, world):
    repo, ids = world
    r = validate(db, repo, cand(decision="Use PostgreSQL", decision_status="accepted",
                                resolution_evidence=[ev(ids["outsider"], "Let's go with PostgreSQL.")]))
    assert r.status == "unresolved" and r.checks[0].state == "verified"  # real comment, but no authority


def _approval_on_pr(db, repo, number, title):
    db.add(PullRequest(repository_id=repo.id, github_id=number, node_id=f"PRA{number}", number=number, title=title,
                       state="open", html_url=f"{repo.html_url}/pull/{number}"))
    c = Comment(repository_id=repo.id, github_id=900 + number, node_id=f"REV{number}", kind="review",
                parent_kind="pull_request", parent_number=number, author_login="dave", author_association="OWNER",
                body="Looks right.", review_state="APPROVED", html_url=f"{repo.html_url}/pull/{number}#pullrequestreview-1")
    db.add(c)
    db.commit()
    return f"comment:{c.id}"


def test_maintainer_approval_of_the_implementing_pr_is_explicit(db, world):
    repo, _ = world
    approval = _approval_on_pr(db, repo, 77, "Switch order storage to PostgreSQL")
    r = validate(db, repo, cand(decision="Use PostgreSQL", decision_status="accepted", resolution_evidence=[ev(approval)]))
    assert (r.status, r.determination) == ("accepted", "explicit")


def test_approval_of_an_unrelated_pr_cannot_establish_an_arbitrary_decision(db, world):
    repo, _ = world
    approval = _approval_on_pr(db, repo, 78, "Fix typo in README")
    r = validate(db, repo, cand(decision="Use MongoDB", decision_status="accepted", resolution_evidence=[ev(approval)]))
    assert r.determination != "explicit" and r.decision is None


def test_negated_option_in_a_maintainer_statement_is_never_the_decision(db, world):
    """Security regression: citing "We decided to go with PostgreSQL. MongoDB does not support..." must not let
    a caller record "Use MongoDB" as explicitly accepted."""
    repo, ids = world
    flipped = validate(db, repo, cand(decision="Use MongoDB", decision_status="accepted",
                                      resolution_evidence=[ev(ids["maint"])]))
    assert flipped.determination != "explicit" and flipped.decision is None
    assert any("does not positively name" in n for n in flipped.notes)
    negated = comment(db, repo, 50, "dave", "OWNER", "We decided to use PostgreSQL, not MongoDB.")
    db.commit()
    r = validate(db, repo, cand(decision="Use MongoDB", decision_status="accepted", resolution_evidence=[ev(negated)]))
    assert r.determination != "explicit"
    ok = validate(db, repo, cand(decision="Use PostgreSQL", decision_status="accepted", resolution_evidence=[ev(negated)]))
    assert ok.determination == "explicit"


def test_missing_rejection_reason_is_stored_as_null(db, world):
    repo, ids = world
    d, r = create_decision(db, repo, cand(
        decision="Use PostgreSQL", decision_status="accepted",
        resolution_evidence=[ev(ids["maint"], "We decided to go with PostgreSQL")],
        alternatives=[{"name": "MongoDB", "status": "rejected", "rejection_reason": None,
                       "rejection_evidence": [ev(ids["maint"], "MongoDB does not support the multi-document transactions we need")]}],
    ))
    alt = r.alternatives[0]
    assert alt.status == "rejected" and alt.rejection_reason is None


def test_rejection_without_objection_evidence_is_only_not_selected(db, world):
    repo, ids = world
    r = validate(db, repo, cand(
        decision="Use PostgreSQL", decision_status="accepted",
        resolution_evidence=[ev(ids["maint"], "We decided to go with PostgreSQL")],
        alternatives=[{"name": "MongoDB", "status": "rejected", "rejection_reason": "Too slow", "evidence": [ev(ids["mongo"])]}],
    ))
    alt = r.alternatives[0]
    assert alt.status == "considered_not_selected" and alt.rejection_reason is None
    assert any("Too slow" not in n and "MongoDB" in n for n in r.notes)


def test_inferred_decision_without_explicit_approval(db, world):
    repo, ids = world
    r = validate(db, repo, cand(decision="Use PostgreSQL", decision_status="accepted",
                                resolution_evidence=[ev(ids["pr"])]))  # merged PR, nobody approved it in words
    assert (r.status, r.determination) == ("accepted", "inferred")
    assert r.requires_human_review and r.verification_state == "needs_human_review"


def test_reason_without_evidence_is_flagged(db, world):
    repo, ids = world
    r = validate(db, repo, cand(reasoning=[{"reason": "It is web scale", "evidence": []}]))
    assert r.checks[0].flags == ["no_evidence"]


def test_ai_claimed_conflict_is_kept_for_review(db, world):
    repo, ids = world
    r = validate(db, repo, cand(conflict_detected=True, positions=[
        {"alternative": "MongoDB", "stance": "support", "evidence": ev(ids["mongo"])}]))
    assert r.conflict_detected and r.requires_human_review


def test_permission_levels():
    assert permission_level({"admin": True, "push": True}) == "admin"
    assert permission_level({"push": True, "pull": True}) == "write"
    assert permission_level({"triage": True}) == "triage"
    assert permission_level({"pull": True}) == "read"
    assert permission_level({}) == "none"


# ---------------------------------------------------------------- Prompt 9: human review through the API

TOKENS = {"write-token": Reviewer("dave", "write"), "read-token": Reviewer("erin", "read")}


@pytest.fixture
def api(session_factory):
    def db_override():
        with session_factory() as s:
            yield s

    def verifier(token, owner, name):
        from app.services.github.errors import Unauthorized
        if token not in TOKENS:
            raise Unauthorized("bad token")
        return TOKENS[token]

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_reviewer_verifier] = lambda: verifier
    yield TestClient(app, headers=ADMIN)
    app.dependency_overrides.clear()


def conflict_payload(ids):
    return cand(
        positions=[{"alternative": "MongoDB", "stance": "support", "evidence": ev(ids["mongo"])},
                   {"alternative": "PostgreSQL", "stance": "support", "evidence": ev(ids["pg"])}],
        alternatives=[{"name": "MongoDB", "evidence": [ev(ids["mongo"])]}, {"name": "PostgreSQL", "evidence": [ev(ids["pg"])]}],
    ).model_dump()


def test_api_validate_create_review_supersede(api, world):
    repo, ids = world
    dry = api.post(f"/api/repositories/{repo.id}/decisions/validate", json=conflict_payload(ids)).json()
    assert dry["decision_status"] == "unresolved" and dry["would_create"]
    assert api.get(f"/api/repositories/{repo.id}/decisions").json() == []  # dry run stored nothing

    d = api.post(f"/api/repositories/{repo.id}/decisions", json=conflict_payload(ids))
    assert d.status_code == 201
    did = d.json()["id"]
    body = {"outcome_status": "accepted", "selected_alternative": "PostgreSQL",
            "rejected_alternatives": [{"name": "MongoDB", "reason": None}],
            "explanation": "Maintainers agreed in the sync meeting; see issue #12."}

    assert api.post(f"/api/decisions/{did}/reviews", json=body).status_code == 401  # no token
    assert api.post(f"/api/decisions/{did}/reviews", json=body, headers={"X-GitHub-Token": "nope"}).status_code == 401
    forbidden = api.post(f"/api/decisions/{did}/reviews", json=body, headers={"X-GitHub-Token": "read-token"})
    assert forbidden.status_code == 403 and "write access" in forbidden.json()["detail"]

    ok = api.post(f"/api/decisions/{did}/reviews", json=body, headers={"X-GitHub-Token": "write-token"}).json()
    assert (ok["status"], ok["determination"], ok["decision"]) == ("accepted", "human_confirmed", "PostgreSQL")
    assert {a["name"]: a["status"] for a in ok["alternatives"]} == {"MongoDB": "rejected", "PostgreSQL": "selected"}
    assert ok["reviews"][0]["reviewer_login"] == "dave" and ok["reviews"][0]["reviewer_permission"] == "write"
    assert ok["conflict_detected"] is True  # history of disagreement is preserved
    assert ok["history"][-1]["snapshot"]["status"] == "unresolved"  # previous state kept in the audit log

    new = api.post(f"/api/repositories/{repo.id}/decisions", json=conflict_payload(ids)).json()
    sup = api.post(f"/api/decisions/{did}/supersede", json={"superseded_by_id": new["id"], "explanation": "Moved to a new storage design."},
                   headers={"X-GitHub-Token": "write-token"}).json()
    assert sup["status"] == "superseded" and sup["superseded_by_id"] == new["id"]
    assert [e["event"] for e in sup["history"]] == ["created", "reviewed", "superseded"]
    again = api.post(f"/api/decisions/{did}/reviews", json=body, headers={"X-GitHub-Token": "write-token"})
    assert again.status_code == 422


def test_api_refuses_unsupported_candidate(api, world):
    repo, _ = world
    r = api.post(f"/api/repositories/{repo.id}/decisions", json=cand(
        decision="Use MySQL", decision_status="accepted", resolution_evidence=[ev("comment_101")]).model_dump())
    assert r.status_code == 422 and r.json()["detail"]["report"]["verification_state"] == "unsupported"


def test_review_validation_errors(api, world):
    repo, ids = world
    did = api.post(f"/api/repositories/{repo.id}/decisions", json=conflict_payload(ids)).json()["id"]
    h = {"X-GitHub-Token": "write-token"}
    bad_alt = {"outcome_status": "accepted", "selected_alternative": "Cassandra", "explanation": "Long enough reason."}
    assert api.post(f"/api/decisions/{did}/reviews", json=bad_alt, headers=h).status_code == 422
    no_outcome = {"outcome_status": "accepted", "explanation": "Long enough reason."}
    assert api.post(f"/api/decisions/{did}/reviews", json=no_outcome, headers=h).status_code == 422
    short = {"outcome_status": "unresolved", "explanation": "no"}
    assert api.post(f"/api/decisions/{did}/reviews", json=short, headers=h).status_code == 422


def test_candidate_endpoints_require_the_admin_token(api, world, monkeypatch):
    from app.core.config import get_settings
    repo, ids = world
    body = conflict_payload(ids)
    for headers in ({"X-DeciTrace-Admin-Token": ""}, {"X-DeciTrace-Admin-Token": "wrong"}):
        assert api.post(f"/api/repositories/{repo.id}/decisions", json=body, headers=headers).status_code == 401
        assert api.post(f"/api/repositories/{repo.id}/decisions/validate", json=body, headers=headers).status_code == 401
    monkeypatch.delenv("DECITRACE_ADMIN_TOKEN")
    get_settings.cache_clear()
    r = api.post(f"/api/repositories/{repo.id}/decisions", json=body)
    assert r.status_code == 403 and "disabled" in r.json()["detail"]
    assert api.post(f"/api/repositories/{repo.id}/index").status_code == 403
    assert api.post(f"/api/repositories/{repo.id}/links/rebuild").status_code == 403
