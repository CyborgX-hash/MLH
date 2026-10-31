"""Dashboard overview, decision list details, timeline and graph: only established relationships."""
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.services.evidence.authority import Reviewer
from app.services.evidence.records import review_decision
from app.services.history.views import graph, overview, timeline
from tests.test_rag import w  # noqa: F401  (fixture)

ALLOWED_EDGE_LABELS = {
    "accepted", "rejected", "considered", "proposed", "deferred", "evidence", "commented on", "argued against",
    "references", "discusses", "implements", "supersedes", "conflicts_with", "related_to", "implemented", "changed",
}


def test_overview_counts_and_recent_activity(db, w):
    o = overview(db, w.repo)
    c = o["counts"]
    assert (c["decisions"], c["accepted"], c["unresolved"], c["rejected_alternatives"]) == (2, 1, 1, 1)
    assert c["needs_review"] == 1 and c["discussions_collected"] == 4  # 3 issues + 1 PR
    assert {a["event"] for a in o["recent_activity"]} == {"created"}


def test_timeline_is_chronological_and_links_sources(db, w):
    ev = timeline(db, w.pg_decision)
    kinds = [e["type"] for e in ev]
    assert "approval" in kinds and "implementation" in kinds and "rejection" in kinds
    assert all(e["url"] for e in ev if e["source"] == "github")
    impl = next(e for e in ev if e["type"] == "implementation")
    assert impl["url"].endswith("/pull/25") and impl["label"] == "Implemented in PR #25"
    dated = [e["at"] for e in ev if e["at"]]
    assert dated == sorted(dated)


def test_unresolved_decision_timeline_has_no_approval(db, w):
    ev = timeline(db, w.queue_decision)
    assert "approval" not in [e["type"] for e in ev]
    assert {e["label"] for e in ev if e["type"] == "proposal"} == {"Kafka proposed or supported", "RabbitMQ proposed or supported"}


def test_human_review_and_supersede_appear_in_timeline(db, w):
    review_decision(db, w.queue_decision, Reviewer("dave", "maintain"), "accepted", "Agreed in the architecture call.",
                    selected_alternative="Kafka")
    ev = timeline(db, w.queue_decision)
    review = next(e for e in ev if e["type"] == "human_review")
    assert "@dave" in review["label"] and review["source"] == "decitrace_review"


def test_graph_contains_only_established_relationships(db, w):
    g = graph(db, w.pg_decision)
    ids = {n["id"] for n in g["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in g["edges"])
    assert {e["label"] for e in g["edges"]} <= ALLOWED_EDGE_LABELS
    labels = {(e["source"], e["target"], e["label"]) for e in g["edges"]}
    d = f"decision:{w.pg_decision.id}"
    assert (d, f"alternative:{w.pg_decision.id}:PostgreSQL", "accepted") in labels
    assert (d, f"alternative:{w.pg_decision.id}:MongoDB", "rejected") in labels
    assert (f"pull_request:{w.p25.id}", d, "implemented") in labels
    assert any(e["label"] == "changed" and e["target"] == "file:src/db.py" for e in g["edges"])
    assert ("user:dave", f"issue:{w.i12.id}", "commented on") in labels
    kinds = {n["kind"] for n in g["nodes"]}
    assert kinds >= {"decision", "alternative", "contributor", "issue", "pull_request", "file"}


def test_unresolved_graph_never_shows_acceptance(db, w):
    g = graph(db, w.queue_decision)
    assert "accepted" not in {e["label"] for e in g["edges"]}
    assert {e["label"] for e in g["edges"] if e["source"].startswith("decision:")} == {"proposed"}


def test_api_overview_list_timeline_graph(session_factory, db, w):
    def db_override():
        with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = db_override
    try:
        api = TestClient(app)
        rid = w.repo.id
        assert api.get(f"/api/repositories/{rid}/overview").json()["counts"]["decisions"] == 2
        items = api.get(f"/api/repositories/{rid}/decisions").json()
        assert items[0]["requires_human_review"] is True  # needs-review first
        pg = next(i for i in items if i["id"] == w.pg_decision.id)
        assert {a["name"]: a["status"] for a in pg["alternatives"]} == {"PostgreSQL": "selected", "MongoDB": "rejected"}
        assert pg["evidence_count"] > 0
        assert api.get(f"/api/decisions/{w.pg_decision.id}/timeline").status_code == 200
        g = api.get(f"/api/decisions/{w.pg_decision.id}/graph").json()
        assert g["nodes"] and g["edges"]
        assert api.get("/api/decisions/9999/graph").status_code == 404
    finally:
        app.dependency_overrides.clear()
