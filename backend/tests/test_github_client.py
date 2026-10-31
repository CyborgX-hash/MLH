import httpx
import pytest

from app.services.github.client import GitHubClient
from app.services.github.errors import (
    BinaryFile, FileTooLarge, Forbidden, GraphQLUnavailable, InvalidPath, InvalidRepositoryURL, NotFound,
    RateLimited, Unavailable,
)
from app.services.github.files import is_safe_path, select_files
from app.services.github.urls import parse_repo_url
from tests.github_fake import O, R, FakeGitHub


@pytest.mark.parametrize("url", [
    "https://github.com/psf/requests", "http://github.com/psf/requests/", "https://www.github.com/psf/requests.git",
    "github.com/psf/requests", "https://github.com/psf/requests/tree/main/src", "https://github.com/psf/requests/issues/1",
    "git@github.com:psf/requests.git", "  https://github.com/psf/requests?tab=readme  ",
])
def test_parse_repo_url_accepts_common_forms(url):
    assert parse_repo_url(url) == ("psf", "requests")


@pytest.mark.parametrize("url", [
    "", "psf/requests", "https://gitlab.com/psf/requests", "https://github.com/psf", "https://github.com/",
    "https://github.com/orgs/psf", "https://github.com/-bad/repo", "https://github.com/psf/..",
    "https://evil.com/github.com/psf/requests", "https://github.com.evil.com/psf/requests", "javascript:alert(1)",
    "https://github.com/a/" + "x" * 300,
])
def test_parse_repo_url_rejects_invalid(url):
    with pytest.raises(InvalidRepositoryURL):
        parse_repo_url(url)


@pytest.mark.parametrize("path,ok", [
    ("src/db.py", True), ("../etc/passwd", False), ("/etc/passwd", False), ("a/../../b", False), ("a//b", False),
    ("a\\b", False), ("a/./b", False), ("x\x00y", False), ("~/.ssh/id_rsa", False), ("", False),
])
def test_is_safe_path(path, ok):
    assert is_safe_path(path) is ok


def test_select_files_prioritises_decision_docs_and_skips_junk():
    entries = FakeGitHub().tree["tree"] + [
        {"path": "big.py", "type": "blob", "sha": "1" * 40, "size": 10_000_000},
        {"path": "package-lock.json", "type": "blob", "sha": "2" * 40, "size": 10},
        {"path": "tests/test_db.py", "type": "blob", "sha": "3" * 40, "size": 10},
        {"path": "../escape.py", "type": "blob", "sha": "4" * 40, "size": 10},
    ]
    files, skipped = select_files(entries, max_files=3, max_bytes=200_000)
    assert [f.path for f in files] == ["README.md", "docs/adr/0001-database.md", "src/db.py"]
    assert skipped == {"dependency_or_generated": 2, "binary": 1, "too_large": 1, "unsafe_path": 1, "over_file_limit": 1}


def test_token_is_sent_only_when_configured():
    seen = []

    def handler(req):
        seen.append(req.headers.get("authorization"))
        return httpx.Response(200, json={"ok": True})

    GitHubClient(token="secret", transport=httpx.MockTransport(handler)).get_repository("a", "b")
    GitHubClient(token=None, transport=httpx.MockTransport(handler)).get_repository("a", "b")
    assert seen == ["Bearer secret", None]


def test_issues_exclude_pull_requests_and_paginate():
    fake = FakeGitHub()
    fake.page_size = 1
    issues = list(fake.client().get_issues(O, R))
    assert [i["number"] for i in issues] == [1, 3]  # #2 is a pull request
    assert fake.count(f"/repos/{O}/{R}/issues") == 3  # followed every Link: rel="next"


def test_pull_requests_stop_at_updated_since():
    fake = FakeGitHub()
    fake.pulls = [{"number": 9, "updated_at": "2026-10-09T00:00:00Z"}, {"number": 8, "updated_at": "2026-10-01T00:00:00Z"}]
    got = list(fake.client().get_pull_requests(O, R, updated_since="2026-10-05T00:00:00Z"))
    assert [p["number"] for p in got] == [9]


def test_limit_stops_pagination_early():
    fake = FakeGitHub()
    fake.page_size = 1
    fake.commits = fake.commits * 5
    assert len(list(fake.client().get_commits(O, R, limit=2))) == 2
    assert fake.count(f"/repos/{O}/{R}/commits") == 2


def test_primary_rate_limit_waits_when_reset_is_near_then_succeeds():
    responses = iter([
        httpx.Response(403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1010"}, json={}),
        httpx.Response(200, json={"id": 1}),
    ])
    waits = []
    client = GitHubClient(transport=httpx.MockTransport(lambda r: next(responses)), sleep=waits.append, clock=lambda: 1000)
    assert client.get_repository("a", "b") == {"id": 1}
    assert waits == [11]


def test_primary_rate_limit_raises_when_reset_is_far():
    resp = httpx.Response(403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "5000"}, json={})
    client = GitHubClient(transport=httpx.MockTransport(lambda r: resp), sleep=lambda s: None, clock=lambda: 1000)
    with pytest.raises(RateLimited) as exc:
        client.get_repository("a", "b")
    assert exc.value.reset_at == 5000 and "GITHUB_TOKEN" in str(exc.value)


def test_secondary_rate_limit_honours_retry_after():
    responses = iter([httpx.Response(429, headers={"retry-after": "3"}), httpx.Response(200, json={})])
    waits = []
    GitHubClient(transport=httpx.MockTransport(lambda r: next(responses)), sleep=waits.append).get_repository("a", "b")
    assert waits == [3.0]


def test_plain_403_is_forbidden_not_rate_limit():
    client = GitHubClient(transport=httpx.MockTransport(lambda r: httpx.Response(403, json={"message": "Must have admin"})))
    with pytest.raises(Forbidden):
        client.get_repository("a", "b")


def test_server_errors_retry_with_backoff_then_give_up():
    waits = []
    client = GitHubClient(transport=httpx.MockTransport(lambda r: httpx.Response(502)), sleep=waits.append, max_retries=2)
    with pytest.raises(Unavailable):
        client.get_repository("a", "b")
    assert waits == [1, 2]


def test_network_errors_retry():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json={"id": 2})

    assert GitHubClient(transport=httpx.MockTransport(handler), sleep=lambda s: None).get_repository("a", "b") == {"id": 2}


def test_not_found_maps_to_typed_error():
    with pytest.raises(NotFound):
        FakeGitHub().client().get_repository("nobody", "nothing")


def test_issues_disabled_returns_empty():
    fake = FakeGitHub()
    fake.fail[f"/repos/{O}/{R}/issues"] = lambda: httpx.Response(410, json={"message": "Issues are disabled"})
    assert list(fake.client().get_issues(O, R)) == []


def test_file_content_decodes_text_and_guards_size_binary_and_paths():
    fake = FakeGitHub()
    gh = fake.client()
    assert gh.get_file_content(O, R, "src/db.py") == "import psycopg\n"
    with pytest.raises(FileTooLarge):
        gh.get_file_content(O, R, "README.md", max_bytes=3)
    fake.contents["img.dat"] = b"\x89PNG\x00\x00"
    with pytest.raises(BinaryFile):
        gh.get_file_content(O, R, "img.dat")
    before = sum(fake.calls.values())
    with pytest.raises(InvalidPath):
        gh.get_file_content(O, R, "../../secrets")
    assert sum(fake.calls.values()) == before  # rejected before any request


def test_graphql_requires_token():
    with pytest.raises(GraphQLUnavailable):
        list(FakeGitHub().client(token=None).get_discussions(O, R))


def test_discussions_and_threaded_comments():
    fake = FakeGitHub()
    gh = fake.client()
    discussions = list(gh.get_discussions(O, R))
    assert [d["number"] for d in discussions] == [7]
    comments = list(gh.get_discussion_comments("D_1"))
    assert [(c["id"], c["reply_to"]) for c in comments] == [("DC_1", None), ("DC_2", "DC_1")]


def test_discussions_disabled_yields_nothing():
    fake = FakeGitHub()
    fake.repo["has_discussions"] = False
    assert list(fake.client().get_discussions(O, R)) == []


def test_graphql_errors_are_typed():
    resp = httpx.Response(200, json={"data": None, "errors": [{"type": "NOT_FOUND", "message": "x"}]})
    client = GitHubClient(token="t", transport=httpx.MockTransport(lambda r: resp))
    with pytest.raises(NotFound):
        list(client.get_discussions("a", "b"))
