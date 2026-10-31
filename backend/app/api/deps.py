"""FastAPI dependencies. Tests override these to inject a mocked GitHub and a test database."""
import hmac
from typing import Callable, Iterator, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal, get_db
from app.services.github.client import GitHubClient
from app.workers.ingestion import run_sync

SyncRunner = Callable[[int], None]


def require_admin(
    x_decitrace_admin_token: Optional[str] = Header(None), settings: Settings = Depends(get_settings)
) -> None:
    """Gate for endpoints that write decision candidates or rebuild indexes.

    Decision candidates normally come from the in-process extractor; over HTTP they must carry the server's
    admin token, so an anonymous caller cannot inject or flag decisions.
    """
    expected = settings.decitrace_admin_token
    if not expected:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This endpoint is disabled. Set DECITRACE_ADMIN_TOKEN on the server to enable it.")
    if not x_decitrace_admin_token or not hmac.compare_digest(x_decitrace_admin_token.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "A valid X-DeciTrace-Admin-Token header is required.")


def make_github_client(settings: Settings) -> GitHubClient:
    return GitHubClient(token=settings.github_token or None)


def get_github_client(settings: Settings = Depends(get_settings)) -> Iterator[GitHubClient]:
    client = make_github_client(settings)
    try:
        yield client
    finally:
        client.close()


def get_sync_runner(settings: Settings = Depends(get_settings)) -> SyncRunner:
    def runner(job_id: int) -> None:
        from app.services.ai.client import AIClient

        run_sync(job_id, SessionLocal, lambda: make_github_client(settings),
                 ai_factory=lambda: AIClient.from_settings(settings))

    return runner


__all__ = ["get_db", "get_github_client", "get_sync_runner", "Session"]
