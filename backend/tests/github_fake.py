"""A fake GitHub API (REST + GraphQL) for tests, served through httpx.MockTransport.

Data shapes follow GitHub's documented responses, reduced to the fields DeciTrace reads.
"""
import base64
import json
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import httpx

from app.services.github.client import GitHubClient

O, R = "acme", "widgets"
BASE = f"https://github.com/{O}/{R}"
API = f"https://api.github.com/repos/{O}/{R}"


def user(login: str) -> dict:
    return {"login": login, "id": hash(login) % 10_000}


def repo_json(**over) -> dict:
    data = {
        "id": 4242, "node_id": "R_4242", "name": R, "full_name": f"{O}/{R}", "owner": user(O), "private": False,
        "visibility": "public", "html_url": BASE, "description": "Widgets", "default_branch": "main",
        "language": "Python", "license": {"spdx_id": "MIT"}, "stargazers_count": 7, "forks_count": 1,
        "archived": False, "has_issues": True, "has_discussions": True,
        "created_at": "2024-01-01T00:00:00Z", "pushed_at": "2026-10-01T00:00:00Z",
    }
    data.update(over)
    return data


def issue(n: int, updated: str = "2026-10-01T00:00:00Z", pr: bool = False) -> dict:
    data = {
        "id": 1000 + n, "node_id": f"I_{n}", "number": n, "title": f"Issue {n}", "body": f"Body {n}",
        "state": "closed", "state_reason": "completed", "user": user("alice"), "author_association": "MEMBER",
        "labels": [{"name": "design"}], "comments": 1, "html_url": f"{BASE}/issues/{n}",
        "created_at": "2026-09-01T00:00:00Z", "updated_at": updated, "closed_at": None,
    }
    if pr:
        data["pull_request"] = {"url": f"{API}/pulls/{n}"}
        data["html_url"] = f"{BASE}/pull/{n}"
    return data


def issue_comment(cid: int, n: int, on_pr: bool = False) -> dict:
    kind = "pull" if on_pr else "issues"
    return {
        "id": cid, "node_id": f"IC_{cid}", "user": user("bob"), "author_association": "CONTRIBUTOR",
        "body": f"Comment {cid}", "html_url": f"{BASE}/{kind}/{n}#issuecomment-{cid}",
        "issue_url": f"{API}/issues/{n}", "created_at": "2026-09-02T00:00:00Z", "updated_at": "2026-09-02T00:00:00Z",
    }


def pull(n: int, updated: str = "2026-10-01T00:00:00Z") -> dict:
    return {
        "id": 2000 + n, "node_id": f"PR_{n}", "number": n, "title": f"PR {n}", "body": "Use PostgreSQL",
        "state": "closed", "draft": False, "user": user("carol"), "author_association": "MEMBER", "labels": [],
        "base": {"ref": "main"}, "head": {"ref": f"feat-{n}", "sha": "a" * 40}, "merge_commit_sha": "b" * 40,
        "html_url": f"{BASE}/pull/{n}", "created_at": "2026-09-01T00:00:00Z", "updated_at": updated,
        "closed_at": "2026-09-05T00:00:00Z", "merged_at": "2026-09-05T00:00:00Z",
    }


class FakeGitHub:
    """Routes requests to canned data. Counts requests per path so tests can assert what was skipped."""

    def __init__(self):
        self.repo = repo_json()
        self.issues: List[dict] = [issue(1), issue(2, pr=True), issue(3)]
        self.issue_comments: List[dict] = [issue_comment(11, 1), issue_comment(12, 2, on_pr=True)]
        self.pulls: List[dict] = [pull(2)]
        self.reviews = {2: [{"id": 31, "node_id": "PRR_31", "user": user("dave"), "body": "LGTM",
                             "state": "APPROVED", "html_url": f"{BASE}/pull/2#pullrequestreview-31",
                             "commit_id": "a" * 40, "submitted_at": "2026-09-04T00:00:00Z"}]}
        self.files = {2: [{"filename": "src/db.py", "previous_filename": "src/database.py", "status": "renamed",
                           "additions": 3, "deletions": 1, "sha": "c" * 40}]}
        self.review_comments = [{
            "id": 41, "node_id": "PRRC_41", "user": user("dave"), "body": "Why not MongoDB?",
            "html_url": f"{BASE}/pull/2#discussion_r41", "pull_request_url": f"{API}/pulls/2", "path": "src/db.py",
            "line": 3, "commit_id": "a" * 40, "in_reply_to_id": None,
            "created_at": "2026-09-03T00:00:00Z", "updated_at": "2026-09-03T00:00:00Z",
        }]
        self.commits = [{
            "sha": "d" * 40, "html_url": f"{BASE}/commit/{'d' * 40}", "author": user("carol"),
            "committer": user("carol"), "parents": [{"sha": "e" * 40}],
            "commit": {"message": "Switch to PostgreSQL (#2)",
                       "author": {"name": "Carol", "email": "carol@example.com", "date": "2026-09-05T00:00:00Z"},
                       "committer": {"name": "Carol", "email": "carol@example.com", "date": "2026-09-05T00:00:00Z"}},
        }]
        self.tree = {"truncated": False, "tree": [
            {"path": "README.md", "type": "blob", "sha": "f1" * 20, "size": 40},
            {"path": "docs/adr/0001-database.md", "type": "blob", "sha": "f2" * 20, "size": 60},
            {"path": "src/db.py", "type": "blob", "sha": "f3" * 20, "size": 30},
            {"path": "node_modules/x/index.js", "type": "blob", "sha": "f4" * 20, "size": 10},
            {"path": "logo.png", "type": "blob", "sha": "f5" * 20, "size": 10},
            {"path": "src", "type": "tree", "sha": "f6" * 20},
        ]}
        self.contents = {
            "README.md": b"# Widgets\n",
            "docs/adr/0001-database.md": b"# Use PostgreSQL\nWe chose PostgreSQL over MongoDB.\n",
            "src/db.py": b"import psycopg\n",
        }
        self.discussions = [{
            "id": "D_1", "databaseId": 51, "number": 7, "title": "Which queue?", "body": "Kafka or SQS?",
            "url": f"{BASE}/discussions/7", "createdAt": "2026-09-01T00:00:00Z", "updatedAt": "2026-10-01T00:00:00Z",
            "closed": False, "closedAt": None, "category": {"name": "Ideas"}, "author": {"login": "erin"},
            "answer": None,
        }]
        self.discussion_comments = {"D_1": [{
            "id": "DC_1", "databaseId": 61, "url": f"{BASE}/discussions/7#discussioncomment-61", "body": "SQS",
            "createdAt": "2026-09-02T00:00:00Z", "updatedAt": "2026-09-02T00:00:00Z", "authorAssociation": "MEMBER",
            "author": {"login": "frank"},
            "replies": {"nodes": [{
                "id": "DC_2", "databaseId": 62, "url": f"{BASE}/discussions/7#discussioncomment-62", "body": "+1",
                "createdAt": "2026-09-03T00:00:00Z", "updatedAt": "2026-09-03T00:00:00Z",
                "authorAssociation": "NONE", "author": {"login": "gina"},
            }]},
        }]}
        self.calls: Dict[str, int] = {}
        self.queries: List[Dict[str, List[str]]] = []
        self.fail: Dict[str, Callable[[], httpx.Response]] = {}  # path prefix -> response factory
        self.page_size: Optional[int] = None

    def count(self, prefix: str) -> int:
        return sum(v for k, v in self.calls.items() if k.startswith(prefix))

    def _page(self, request: httpx.Request, items: List[Any]) -> httpx.Response:
        q = parse_qs(urlparse(str(request.url)).query)
        size = self.page_size or int(q.get("per_page", ["100"])[0])
        page = int(q.get("page", ["1"])[0])
        chunk = items[(page - 1) * size : page * size]
        headers = {"x-ratelimit-limit": "60", "x-ratelimit-remaining": "59", "x-ratelimit-reset": "9999999999"}
        if page * size < len(items):
            nxt = request.url.copy_merge_params({"page": str(page + 1), "per_page": str(size)})
            headers["link"] = f'<{nxt}>; rel="next"'
        return httpx.Response(200, json=chunk, headers=headers)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls[path] = self.calls.get(path, 0) + 1
        self.queries.append(parse_qs(urlparse(str(request.url)).query))
        for prefix, make in self.fail.items():
            if path.startswith(prefix):
                return make()
        rp = f"/repos/{O}/{R}"
        if path == "/graphql":
            return self._graphql(json.loads(request.content))
        if path == rp:
            return httpx.Response(200, json=self.repo)
        if path == f"{rp}/issues":
            return self._page(request, self.issues)
        if path == f"{rp}/issues/comments":
            return self._page(request, self.issue_comments)
        if path == f"{rp}/pulls":
            return self._page(request, self.pulls)
        if path == f"{rp}/pulls/comments":
            return self._page(request, self.review_comments)
        if path.startswith(f"{rp}/pulls/"):
            parts = path.split("/")
            n, what = int(parts[5]), parts[6]
            return self._page(request, (self.reviews if what == "reviews" else self.files).get(n, []))
        if path == f"{rp}/commits":
            return self._page(request, self.commits)
        if path.startswith(f"{rp}/git/trees/"):
            return httpx.Response(200, json=self.tree)
        if path.startswith(f"{rp}/contents/"):
            fpath = path[len(f"{rp}/contents/"):]
            if fpath not in self.contents:
                return httpx.Response(404, json={"message": "Not Found"})
            raw = self.contents[fpath]
            return httpx.Response(200, json={"type": "file", "size": len(raw), "encoding": "base64",
                                             "content": base64.b64encode(raw).decode()})
        return httpx.Response(404, json={"message": "Not Found"})

    def _graphql(self, body: dict) -> httpx.Response:
        variables = body["variables"]
        if "openIssues" in body["query"]:
            return httpx.Response(200, json={"data": {"repository": {
                "openIssues": {"totalCount": 2}, "closedIssues": {"totalCount": 5}, "openPRs": {"totalCount": 1},
                "mergedPRs": {"totalCount": 9}, "closedPRs": {"totalCount": 0}, "discussions": {"totalCount": 1},
                "hasDiscussionsEnabled": self.repo.get("has_discussions", False), "stargazerCount": 7,
                "forkCount": 1, "defaultBranchRef": {"target": {"history": {"totalCount": 42}}}}}})
        if "discussions(" in body["query"]:
            enabled = self.repo.get("has_discussions", False)
            return httpx.Response(200, json={"data": {"repository": {
                "hasDiscussionsEnabled": enabled,
                "discussions": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": self.discussions},
            }}})
        comments = [dict(c) for c in self.discussion_comments.get(variables["id"], [])]
        return httpx.Response(200, json={"data": {"node": {"comments": {
            "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": comments}}}})

    def client(self, token: Optional[str] = "test-token", **kw) -> GitHubClient:
        return GitHubClient(token=token, transport=httpx.MockTransport(self.handler), sleep=lambda s: None, **kw)
