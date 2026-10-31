"""Verify who a reviewer is and what they may do in a repository, using GitHub itself.

The reviewer sends their own GitHub token with the review request. It is used for exactly two calls
(`GET /user`, `GET /repos/{owner}/{repo}`), never stored and never logged. Self-declared usernames are
never trusted.
"""
from dataclasses import dataclass

from app.services.github.client import GitHubClient

REVIEW_PERMISSIONS = ("admin", "maintain", "write")


@dataclass(frozen=True)
class Reviewer:
    login: str
    permission: str  # admin|maintain|write|triage|read|none

    @property
    def may_resolve(self) -> bool:
        return self.permission in REVIEW_PERMISSIONS


def permission_level(perms: dict) -> str:
    for key, level in (("admin", "admin"), ("maintain", "maintain"), ("push", "write"), ("triage", "triage"), ("pull", "read")):
        if perms.get(key):
            return level
    return "none"


def verify_reviewer(token: str, owner: str, name: str) -> Reviewer:
    with GitHubClient(token=token) as gh:
        login = gh.get_authenticated_user()["login"]
        perms = gh.get_repository(owner, name).get("permissions") or {}
    return Reviewer(login=login, permission=permission_level(perms))
