import subprocess

import pytest

from decisionlens.codelink import RenameMap, candidate_paths, candidate_symbols, link_decisions
from decisionlens.models import Decision, Evidence, Reason
from decisionlens.pr import parse_diff, render_markdown, surface


def git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True, capture_output=True,
    )


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "parser").mkdir()
    body = "\n".join(f"line {i} of the cache implementation" for i in range(30))
    (tmp_path / "parser" / "cache.py").write_text(f"class ParserCache:\n    pass\n\ndef lookup_entry():\n    pass\n{body}\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "add cache")
    return tmp_path


def make_decision(**kw):
    ev = Evidence(2, "bob", "https://d/2", "global cache leaks memory")
    return Decision(
        decision_id="DEC-1", title=kw.get("title", "global memoization cache"), status="rejected",
        summary=kw.get("summary", "Rejected: it leaks memory"), reasons=[Reason("it leaks memory", [ev])],
        evidence=[ev], source_url="https://d/t/1",
    )


def test_candidate_extraction():
    text = "Use `ParserCache` in parser/cache.py, see lookup_entry and obj.method"
    assert "ParserCache" in candidate_symbols(text)
    assert "lookup_entry" in candidate_symbols(text)
    assert "parser/cache.py" in candidate_paths(text)


def test_links_symbol_to_definition(repo):
    d = make_decision(summary="Rejected in favour of `ParserCache`")
    link_decisions([d], str(repo))
    refs = [r for r in d.code_refs if r.symbol == "ParserCache"]
    assert refs and refs[0].path == "parser/cache.py" and refs[0].kind == "definition" and refs[0].commit


def test_rename_map_follows_moves_across_history(repo):
    git(repo, "mv", "parser/cache.py", "parser/memo.py")
    git(repo, "commit", "-q", "-m", "rename")
    (repo / "parser").rename(repo / "core")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "move dir")
    rm = RenameMap.build(str(repo))
    assert rm.current("parser/cache.py") == "core/memo.py"
    assert rm.current("core/memo.py") == "core/memo.py"


def test_pr_surfaces_decision_after_file_was_renamed(repo):
    d = make_decision(summary="Rejected in favour of `ParserCache` in parser/cache.py")
    link_decisions([d], str(repo))
    git(repo, "mv", "parser/cache.py", "parser/memo.py")
    git(repo, "commit", "-q", "-m", "rename")
    matches = surface([d], ["parser/memo.py"], repo=str(repo), prefer="tfidf")
    assert matches and matches[0].decision is d
    assert any("recorded as parser/cache.py" in r for r in matches[0].reasons)


def test_pr_surfaces_by_symbol_and_text_and_ignores_unrelated():
    d = make_decision(summary="`ParserCache` global memoization cache leaks memory")
    d.code_refs = []
    from decisionlens.models import CodeRef
    d.code_refs = [CodeRef(path="x.py", symbol="ParserCache")]
    other = make_decision(title="logging format", summary="use json logs")
    other.decision_id = "DEC-2"
    other.reasons = []
    diff = "diff --git a/y.py b/y.py\n@@ -1,3 +1,3 @@ class ParserCache\n-def ParserCache():\n+class ParserCache:\n"
    files, symbols = parse_diff(diff)
    assert files == {"y.py"} and "ParserCache" in symbols
    matches = surface([d, other], sorted(files), sorted(symbols), "add a global memoization cache", prefer="tfidf")
    assert matches[0].decision is d
    assert all(m.decision is not other for m in matches)
    md = render_markdown(matches)
    assert "REJECTED earlier" in md and "https://d/2" in md


def test_render_when_nothing_found():
    assert "No related" in render_markdown([])
