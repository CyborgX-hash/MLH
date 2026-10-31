import json
from pathlib import Path

from decisionlens.extract import extract_decisions, ground, reduce_candidates, resolve_status
from decisionlens.llm import HeuristicBackend, OllamaBackend, parse_candidates
from decisionlens.models import Thread, decision_id
from decisionlens.store import load_decisions, save_decisions

FIXTURE = Path(__file__).parent / "fixtures" / "mini_thread.json"


def thread() -> Thread:
    return Thread.from_dict(json.loads(FIXTURE.read_text()))


def test_ground_prefers_verbatim_and_cites_the_right_post():
    ev = ground("it leaks memory in long running processes", thread(), preferred=2)
    assert ev.post_id == 2 and ev.verbatim and ev.author == "bob"
    assert ev.url.endswith("/9999/2")


def test_ground_rejects_hallucinated_claims():
    assert ground("it causes quantum entanglement in the database", thread(), preferred=2) is None


def test_ground_accepts_paraphrase_with_high_overlap():
    ev = ground("global memoization cache leaks memory", thread())
    assert ev is not None and ev.post_id == 2 and not ev.verbatim


def test_heuristic_pipeline_recovers_rejected_idea_with_reason_and_evidence():
    decisions = extract_decisions(thread(), HeuristicBackend())
    rejected = [d for d in decisions if d.status == "rejected"]
    assert rejected, "the global cache must be recovered as rejected"
    d = rejected[0]
    assert d.evidence and d.evidence[0].post_id == 2
    assert any("leaks memory" in r.text for r in d.reasons)
    assert all(r.evidence for r in d.reasons)
    assert not any("Thanks everyone" in d.summary for d in decisions)  # chatter ignored


def test_unverifiable_candidates_are_dropped_unless_requested():
    cand = [{"idea": "Use blockchain", "stance": "rejected", "summary": "", "post_id": 2,
             "quote": "we should use a blockchain ledger", "reasons": ["it is slow"]}]
    assert reduce_candidates(cand, thread()) == []
    assert len(reduce_candidates(cand, thread(), keep_unverified=True)) == 1


def test_duplicate_ideas_across_chunks_are_merged_and_later_stance_wins():
    cands = [
        {"idea": "global memoization cache", "stance": "accepted", "summary": "", "post_id": 1,
         "quote": "I propose a global memoization cache in `parser/cache.py` to speed up repeated parses.", "reasons": []},
        {"idea": "the global memoization cache", "stance": "rejected", "summary": "", "post_id": 4,
         "quote": "drop the global memoization cache", "reasons": []},
    ]
    out = reduce_candidates(cands, thread())
    assert len(out) == 1 and out[0].status == "rejected"
    assert len(out[0].evidence) == 2


def test_resolve_status_weights_recent_posts():
    group = [{"post_id": 1, "stance": "accepted"}, {"post_id": 9, "stance": "rejected"}]
    assert resolve_status(group) == "rejected"


def test_ids_are_deterministic():
    assert decision_id("u", "A  Cache!") == decision_id("u", "a cache")


def test_store_roundtrip(tmp_path):
    decisions = extract_decisions(thread(), HeuristicBackend())
    path = tmp_path / "d.json"
    save_decisions(str(path), decisions, {"backend": "heuristic"})
    loaded, meta = load_decisions(str(path))
    assert meta["backend"] == "heuristic"
    assert [d.to_dict() for d in loaded] == [d.to_dict() for d in decisions]


def test_parse_candidates_is_tolerant():
    assert parse_candidates("garbage") == []
    wrapped = 'Sure! {"candidates":[{"idea":"x y","stance":"rejected","post_id":"3","quote":"q","reasons":"because z"}]}'
    out = parse_candidates(wrapped)
    assert out[0]["post_id"] == 3 and out[0]["reasons"] == ["because z"]


def test_ollama_backend_sends_schema_and_parses(monkeypatch):
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            body = {"candidates": [{"idea": "global cache", "stance": "rejected", "post_id": 2, "quote": "q", "reasons": []}]}
            return json.dumps({"message": {"content": json.dumps(body)}}).encode()

    def fake_urlopen(req, timeout=0):
        seen["payload"] = json.loads(req.data)
        seen["url"] = req.full_url
        return Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    backend = OllamaBackend(model="gemma3:1b")
    out = backend.extract(thread().posts, "t")
    assert seen["url"].endswith("/api/chat")
    assert seen["payload"]["model"] == "gemma3:1b" and seen["payload"]["options"]["temperature"] == 0
    assert "properties" in seen["payload"]["format"]
    assert out[0]["idea"] == "global cache"
    assert backend.name == "ollama:gemma3:1b"
