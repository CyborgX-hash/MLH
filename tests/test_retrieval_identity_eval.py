from decisionlens.evaluate import parse_rejected_ideas, pep_discussion_urls, score
from decisionlens.identity import Account, parse_mailmap, resolve
from decisionlens.models import Decision, Reason
from decisionlens.retrieval import DecisionIndex


def dec(i, title, status, summary="", reasons=()):
    return Decision(f"DEC-{i}", title, status, summary, [Reason(r) for r in reasons])


def test_tfidf_search_ranks_relevant_first_and_filters_status():
    ds = [
        dec(1, "global memoization cache", "rejected", "leaks memory", ["thread safety"]),
        dec(2, "json structured logging", "accepted", "log format"),
    ]
    idx = DecisionIndex(ds, prefer="tfidf")
    assert idx.backend == "tfidf"
    assert idx.search("memory leak cache")[0][1].decision_id == "DEC-1"
    assert idx.search("cache", status="accepted") == []


PEP = """PEP: 9999
Title: Example
Discussions-To: https://discuss.python.org/t/pep-9999-example/123
Post-History: `01-Jan-2026 <https://discuss.python.org/t/123/45>`__

Abstract
========

Something.

Rejected Ideas
==============

Using a global memoization cache
--------------------------------

A global cache was rejected because it leaks memory in long running processes.

Making the parser asynchronous
------------------------------

An async parser was rejected because it complicates the C API considerably.

Acknowledgements
================

Thanks.
"""


def test_parse_pep_rejected_ideas_and_discussion_urls():
    items = parse_rejected_ideas(PEP)
    assert [i.title for i in items] == ["Using a global memoization cache", "Making the parser asynchronous"]
    assert "leaks memory" in items[0].body
    assert pep_discussion_urls(PEP) == ["https://discuss.python.org/t/pep-9999-example/123"]


def test_pep_without_rejected_section():
    assert parse_rejected_ideas("Title: x\n\nAbstract\n========\n\nhi\n") == []


def test_score_matches_ideas_and_reasons():
    truth = parse_rejected_ideas(PEP)
    preds = [
        dec(1, "global memoization cache", "rejected", "", ["it leaks memory in long running processes"]),
        dec(2, "unrelated idea about logging", "rejected"),
        dec(3, "async parser", "accepted"),
    ]
    rep = score(9999, truth, preds)
    assert len(rep.matches) == 1 and rep.matches[0].truth == "Using a global memoization cache"
    assert rep.recall == 0.5 and rep.precision == 0.5
    assert rep.reason_score > 0.3
    assert rep.missed == ["Making the parser asynchronous"]
    assert rep.to_dict()["recovered"] == 1


def test_identity_merges_across_platforms_with_signals():
    accounts = [
        Account("github", "jdoe", "Jane Doe", "jane@example.com"),
        Account("discourse", "jane_d", "Jane Doe", "jane@example.com"),
        Account("discourse", "someone_else", "Bob Roe", "bob@example.com"),
        Account("github", "bobby", "Bob Roe"),
        Account("mailing-list", "j.doe", links=("github:jdoe",)),
    ]
    clusters = resolve(accounts)
    by_size = sorted(clusters, key=lambda c: -len(c.members))
    jane = {m.key for m in by_size[0].members}
    assert jane == {"github:jdoe", "discourse:jane_d", "mailing-list:j.doe"}
    assert "email" in by_size[0].signals and by_size[0].confidence >= 0.7
    # name alone (0.5) is not enough to merge two different handles
    assert len(clusters) == 3


def test_identity_does_not_merge_strangers():
    clusters = resolve([Account("github", "alice", "Alice A"), Account("discourse", "carol", "Carol C")])
    assert len(clusters) == 2


def test_mailmap_links_emails():
    accts = parse_mailmap("Jane Doe <jane@example.com> jdoe <old@corp.com>\n# comment\n")
    assert {a.email for a in accts} == {"jane@example.com"}
    assert len(accts) == 2
