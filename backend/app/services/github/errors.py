"""Typed GitHub failures so callers can react precisely (404 vs rate limit vs outage)."""
from datetime import datetime, timezone
from typing import Optional


class GitHubError(Exception):
    status: int = 502

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        if status is not None:
            self.status = status


class InvalidRepositoryURL(GitHubError):
    status = 422


class NotFound(GitHubError):
    status = 404


class Unauthorized(GitHubError):
    """The configured token is invalid or expired."""

    status = 401


class Forbidden(GitHubError):
    status = 403


class Gone(GitHubError):
    """410: e.g. issues are disabled for the repository."""

    status = 410


class EmptyRepository(GitHubError):
    """409: the repository has no commits yet."""

    status = 409


class Unavailable(GitHubError):
    """5xx, network failure or legal block (451)."""

    status = 503


class GraphQLUnavailable(GitHubError):
    """GitHub's GraphQL API always requires authentication."""

    status = 401


class RateLimited(GitHubError):
    status = 429

    def __init__(self, reset_at: Optional[float]):
        self.reset_at = reset_at
        when = (
            datetime.fromtimestamp(reset_at, tz=timezone.utc).strftime("%H:%M:%S UTC") if reset_at else "later"
        )
        super().__init__(f"GitHub API rate limit reached; it resets at {when}. Set GITHUB_TOKEN for higher limits.")


class InvalidPath(GitHubError):
    status = 400


class FileTooLarge(GitHubError):
    status = 413


class BinaryFile(GitHubError):
    status = 415
