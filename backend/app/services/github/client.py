"""GitHub REST + GraphQL client.

- Pagination follows the `Link: rel="next"` header (REST) or `pageInfo.endCursor` (GraphQL).
- Rate limits: waits for the reset when it is close, otherwise raises RateLimited. Secondary limits honour
  `Retry-After`. 5xx and network errors are retried with exponential backoff.
- The token, if configured, only ever lives in the Authorization header of outgoing requests.
"""
from __future__ import annotations

import base64
import re
import time
from typing import Any, Callable, Dict, Iterator, Optional
from urllib.parse import quote

import httpx

from app.services.github.errors import (
    BinaryFile,
    EmptyRepository,
    FileTooLarge,
    Forbidden,
    GitHubError,
    Gone,
    GraphQLUnavailable,
    InvalidPath,
    NotFound,
    RateLimited,
    Unauthorized,
    Unavailable,
)
from app.services.github.files import is_safe_path

API_URL = "https://api.github.com"
USER_AGENT = "DeciTrace/0.1 (+https://github.com/CyborgX-hash/MLH)"


class GitHubClient:
    def __init__(
        self,
        token: Optional[str] = None,
        base_url: str = API_URL,
        transport: Optional[httpx.BaseTransport] = None,
        timeout: float = 20.0,
        max_retries: int = 3,
        max_rate_wait: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.has_token = bool(token)
        self.max_retries = max_retries
        self.max_rate_wait = max_rate_wait
        self._sleep = sleep
        self._clock = clock
        self.rate_limit: Dict[str, Optional[int]] = {"limit": None, "remaining": None, "reset": None}
        self.requests_made = 0
        self._http = httpx.Client(
            base_url=base_url, headers=headers, timeout=timeout, transport=transport, follow_redirects=True
        )

    # ------------------------------------------------------------------ transport

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _record_rate(self, resp: httpx.Response) -> None:
        for key in ("limit", "remaining", "reset"):
            val = resp.headers.get(f"x-ratelimit-{key}")
            if val is not None and val.isdigit():
                self.rate_limit[key] = int(val)

    def _rate_wait(self, resp: httpx.Response) -> Optional[float]:
        """Seconds to wait if this 403/429 is a rate limit, None if it is a real permission error."""
        retry_after = resp.headers.get("retry-after")
        if retry_after and retry_after.isdigit():
            return float(retry_after)
        if resp.headers.get("x-ratelimit-remaining") == "0":
            reset = int(resp.headers.get("x-ratelimit-reset", "0") or 0)
            return max(reset - self._clock(), 0) + 1
        if resp.status_code == 429 or "rate limit" in resp.text.lower():
            return 60.0
        return None

    def _backoff(self, attempt: int) -> float:
        return min(2 ** attempt, 30)

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            last = attempt == self.max_retries
            try:
                self.requests_made += 1
                resp = self._http.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                if last:
                    raise Unavailable(f"Could not reach GitHub ({exc.__class__.__name__}).") from None
                self._sleep(self._backoff(attempt))
                continue
            self._record_rate(resp)
            code = resp.status_code
            if code in (403, 429):
                wait = self._rate_wait(resp)
                if wait is None:
                    raise Forbidden("GitHub denied access to this resource.")
                if wait > self.max_rate_wait or last:
                    reset = self.rate_limit.get("reset") or (self._clock() + wait)
                    raise RateLimited(float(reset))
                self._sleep(wait)
                continue
            if code >= 500:
                if last:
                    raise Unavailable(f"GitHub returned {code}.")
                self._sleep(self._backoff(attempt))
                continue
            if code == 401:
                raise Unauthorized("GitHub rejected the configured token (401). Check GITHUB_TOKEN.")
            if code == 404:
                raise NotFound("Not found on GitHub.")
            if code == 409:
                raise EmptyRepository("The repository is empty.")
            if code == 410:
                raise Gone("This GitHub feature is disabled for the repository.")
            if code == 451:
                raise Unavailable("This repository is unavailable for legal reasons.", status=451)
            if code >= 400:
                raise GitHubError(f"GitHub returned {code}.", status=502)
            return resp
        raise Unavailable("GitHub request failed after retries.")  # pragma: no cover

    def _get(self, url: str, params: Optional[dict] = None) -> Any:
        return self._request("GET", url, params=params).json()

    def _paginate(
        self,
        url: str,
        params: Optional[dict] = None,
        limit: Optional[int] = None,
        stop: Optional[Callable[[dict], bool]] = None,
        keep: Optional[Callable[[dict], bool]] = None,
        max_pages: Optional[int] = None,
    ) -> Iterator[dict]:
        """Yield items across pages. `keep` filters items; `limit` counts kept items; `stop` ends early."""
        query = {"per_page": 100, **(params or {})}
        count = pages = 0
        next_url: Optional[str] = url
        while next_url and (max_pages is None or pages < max_pages):
            pages += 1
            resp = self._request("GET", next_url, params=query)
            for item in resp.json():
                if stop and stop(item):
                    return
                if keep and not keep(item):
                    continue
                yield item
                count += 1
                if limit is not None and count >= limit:
                    return
            next_url = resp.links.get("next", {}).get("url")
            query = None  # the next link already carries every query parameter

    @staticmethod
    def _repo(owner: str, repo: str) -> str:
        return f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"

    # ------------------------------------------------------------------ REST

    def get_repository(self, owner: str, repo: str) -> dict:
        """With a token, the response includes `permissions` for the authenticated user."""
        return self._get(self._repo(owner, repo))

    def get_repository_stats(self, owner: str, repo: str) -> Dict[str, Any]:
        """Totals as GitHub reports them. One GraphQL query with a token; without one, REST search counts
        (Discussions cannot be counted without a token). Values that cannot be read are None."""
        if self.has_token:
            data = self.graphql(STATS_QUERY, {"owner": owner, "name": repo}).get("repository") or {}
            history = ((data.get("defaultBranchRef") or {}).get("target") or {}).get("history") or {}
            total = lambda k: (data.get(k) or {}).get("totalCount")  # noqa: E731
            return {
                "open_issues": total("openIssues"), "closed_issues": total("closedIssues"),
                "open_prs": total("openPRs"), "merged_prs": total("mergedPRs"), "closed_prs": total("closedPRs"),
                "commits": history.get("totalCount"), "discussions": total("discussions"),
                "discussions_enabled": bool(data.get("hasDiscussionsEnabled")),
                "stars": data.get("stargazerCount"), "forks": data.get("forkCount"), "source": "graphql",
            }
        base = f"repo:{owner}/{repo}"
        def search(q: str) -> Optional[int]:
            try:
                return int(self._get("/search/issues", {"q": f"{base} {q}", "per_page": 1}).get("total_count"))
            except (GitHubError, TypeError, ValueError):
                return None
        meta = self.get_repository(owner, repo)
        return {
            "open_issues": search("is:issue is:open"), "closed_issues": search("is:issue is:closed"),
            "open_prs": search("is:pr is:open"), "merged_prs": search("is:pr is:merged"),
            "closed_prs": search("is:pr is:closed is:unmerged"), "commits": self.count_commits(owner, repo),
            "discussions": None, "discussions_enabled": bool(meta.get("has_discussions")),
            "stars": meta.get("stargazers_count"), "forks": meta.get("forks_count"), "source": "rest",
        }

    def count_commits(self, owner: str, repo: str) -> Optional[int]:
        """Commits on the default branch: with one commit per page, the last page number is the total."""
        try:
            resp = self._request("GET", f"{self._repo(owner, repo)}/commits", params={"per_page": 1})
        except (GitHubError, EmptyRepository):
            return None
        last = resp.links.get("last", {}).get("url")
        if not last:
            return len(resp.json())
        m = re.search(r"[?&]page=(\d+)", last)
        return int(m.group(1)) if m else None

    def get_authenticated_user(self) -> dict:
        return self._get("/user")

    def get_repository_tree(self, owner: str, repo: str, ref: str) -> dict:
        """Recursive tree listing (paths, blob SHAs, sizes). Never downloads file contents."""
        try:
            return self._get(f"{self._repo(owner, repo)}/git/trees/{quote(ref, safe='')}", {"recursive": "1"})
        except EmptyRepository:
            return {"tree": [], "truncated": False}

    def get_file_content(self, owner: str, repo: str, path: str, ref: Optional[str] = None, max_bytes: int = 200_000) -> str:
        if not is_safe_path(path):
            raise InvalidPath(f"Refusing unsafe path: {path!r}")
        url = f"{self._repo(owner, repo)}/contents/{quote(path, safe='/')}"
        data = self._get(url, {"ref": ref} if ref else None)
        if not isinstance(data, dict) or data.get("type") != "file":
            raise InvalidPath(f"{path} is not a file.")
        if int(data.get("size") or 0) > max_bytes:
            raise FileTooLarge(f"{path} is larger than {max_bytes} bytes.")
        if data.get("encoding") != "base64" or not data.get("content"):
            raise FileTooLarge(f"{path} content is not available inline.")
        raw = base64.b64decode(data["content"])
        if b"\x00" in raw[:8000]:
            raise BinaryFile(f"{path} is binary.")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            raise BinaryFile(f"{path} is not UTF-8 text.") from None

    def get_issues(self, owner: str, repo: str, since: Optional[str] = None, limit: Optional[int] = None) -> Iterator[dict]:
        """Issues only. GitHub's issues endpoint also returns pull requests; those carry a
        `pull_request` key and are filtered out here (they are fetched through get_pull_requests)."""
        params = {"state": "all", "sort": "updated", "direction": "desc"}
        if since:
            params["since"] = since
        # Pull requests are filtered out after download, so cap pages to keep PR-heavy repositories cheap.
        max_pages = None if limit is None else limit // 100 + 3
        try:
            yield from self._paginate(
                f"{self._repo(owner, repo)}/issues", params, limit=limit,
                keep=lambda i: "pull_request" not in i, max_pages=max_pages,
            )
        except Gone:  # issues disabled
            return

    def get_issue_comments(
        self, owner: str, repo: str, issue_number: Optional[int] = None, since: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Iterator[dict]:
        """Comments on one issue, or repository-wide when issue_number is None. Repository-wide results
        include conversation comments on pull requests (GitHub models a PR as an issue)."""
        params: Dict[str, str] = {}
        if since:
            params["since"] = since
        if issue_number is None:
            url = f"{self._repo(owner, repo)}/issues/comments"
            params.update(sort="updated", direction="desc")
        else:
            url = f"{self._repo(owner, repo)}/issues/{int(issue_number)}/comments"
        try:
            yield from self._paginate(url, params, limit=limit)
        except Gone:
            return

    def get_pull_requests(
        self, owner: str, repo: str, updated_since: Optional[str] = None, limit: Optional[int] = None
    ) -> Iterator[dict]:
        """Most recently updated first. The pulls endpoint has no `since`, so iteration stops at the
        first pull request older than updated_since (ISO-8601 strings compare chronologically)."""
        stop = (lambda pr: pr.get("updated_at", "") < updated_since) if updated_since else None
        params = {"state": "all", "sort": "updated", "direction": "desc"}
        yield from self._paginate(f"{self._repo(owner, repo)}/pulls", params, limit=limit, stop=stop)

    def get_pull_request_reviews(self, owner: str, repo: str, number: int) -> Iterator[dict]:
        yield from self._paginate(f"{self._repo(owner, repo)}/pulls/{int(number)}/reviews")

    def get_pull_request_review_comments(
        self, owner: str, repo: str, number: Optional[int] = None, since: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Iterator[dict]:
        params: Dict[str, str] = {}
        if number is None:
            url = f"{self._repo(owner, repo)}/pulls/comments"
            params.update(sort="updated", direction="desc")
            if since:
                params["since"] = since
        else:
            url = f"{self._repo(owner, repo)}/pulls/{int(number)}/comments"
        yield from self._paginate(url, params, limit=limit)

    def get_pull_request(self, owner: str, repo: str, number: int) -> dict:
        return self._get(f"{self._repo(owner, repo)}/pulls/{int(number)}")

    def get_pull_request_files(self, owner: str, repo: str, number: int, limit: int = 3000) -> Iterator[dict]:
        yield from self._paginate(f"{self._repo(owner, repo)}/pulls/{int(number)}/files", limit=limit)

    def get_commits(
        self, owner: str, repo: str, sha: Optional[str] = None, since: Optional[str] = None,
        path: Optional[str] = None, limit: Optional[int] = None,
    ) -> Iterator[dict]:
        params: Dict[str, str] = {}
        if sha:
            params["sha"] = sha
        if since:
            params["since"] = since
        if path:
            if not is_safe_path(path):
                raise InvalidPath(f"Refusing unsafe path: {path!r}")
            params["path"] = path
        try:
            yield from self._paginate(f"{self._repo(owner, repo)}/commits", params, limit=limit)
        except EmptyRepository:
            return

    # ------------------------------------------------------------------ GraphQL

    def graphql(self, query: str, variables: Dict[str, Any]) -> dict:
        if not self.has_token:
            raise GraphQLUnavailable("GitHub's GraphQL API requires GITHUB_TOKEN.")
        body = self._request("POST", "/graphql", json={"query": query, "variables": variables}).json()
        errors = body.get("errors") or []
        if errors and not body.get("data"):
            kinds = {e.get("type") for e in errors}
            if "NOT_FOUND" in kinds:
                raise NotFound("Not found on GitHub (GraphQL).")
            if "RATE_LIMITED" in kinds:
                raise RateLimited(self.rate_limit.get("reset"))
            raise GitHubError(f"GitHub GraphQL error: {errors[0].get('message', 'unknown')}")
        return body.get("data") or {}

    def get_discussions(
        self, owner: str, repo: str, updated_since: Optional[str] = None, limit: Optional[int] = None
    ) -> Iterator[dict]:
        """Discussions, most recently updated first. Yields nothing when Discussions are disabled."""
        cursor, count = None, 0
        while True:
            data = self.graphql(DISCUSSIONS_QUERY, {"owner": owner, "name": repo, "cursor": cursor})
            repository = data.get("repository")
            if not repository or not repository.get("hasDiscussionsEnabled"):
                return
            page = repository["discussions"]
            for node in page["nodes"]:
                if updated_since and node["updatedAt"] < updated_since:
                    return
                yield node
                count += 1
                if limit is not None and count >= limit:
                    return
            if not page["pageInfo"]["hasNextPage"]:
                return
            cursor = page["pageInfo"]["endCursor"]

    def get_discussion_comments(self, discussion_node_id: str) -> Iterator[dict]:
        """Top-level comments and their replies (first 50 replies per comment). Replies carry
        `reply_to` with the parent comment's node id."""
        cursor = None
        while True:
            data = self.graphql(DISCUSSION_COMMENTS_QUERY, {"id": discussion_node_id, "cursor": cursor})
            node = data.get("node") or {}
            page = node.get("comments")
            if not page:
                return
            for comment in page["nodes"]:
                replies = (comment.pop("replies", None) or {}).get("nodes", [])
                yield {**comment, "reply_to": None}
                for reply in replies:
                    yield {**reply, "reply_to": comment["id"]}
            if not page["pageInfo"]["hasNextPage"]:
                return
            cursor = page["pageInfo"]["endCursor"]


_COMMENT_FIELDS = "id databaseId url body createdAt updatedAt authorAssociation author { login }"

STATS_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    openIssues: issues(states: OPEN) { totalCount }
    closedIssues: issues(states: CLOSED) { totalCount }
    openPRs: pullRequests(states: OPEN) { totalCount }
    mergedPRs: pullRequests(states: MERGED) { totalCount }
    closedPRs: pullRequests(states: CLOSED) { totalCount }
    discussions { totalCount }
    hasDiscussionsEnabled
    stargazerCount
    forkCount
    defaultBranchRef { target { ... on Commit { history { totalCount } } } }
  }
}
"""

DISCUSSIONS_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    hasDiscussionsEnabled
    discussions(first: 50, after: $cursor, orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id databaseId number title body url createdAt updatedAt closed closedAt
        category { name } author { login } answer { id }
      }
    }
  }
}
"""

DISCUSSION_COMMENTS_QUERY = (
    """
query($id: ID!, $cursor: String) {
  node(id: $id) {
    ... on Discussion {
      comments(first: 50, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { %s replies(first: 50) { nodes { %s } } }
      }
    }
  }
}
"""
    % (_COMMENT_FIELDS, _COMMENT_FIELDS)
)
