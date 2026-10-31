"""FastAPI dependencies. Tests override these to inject a mocked GitHub and a test database."""
from typing import Callable, Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal, get_db
from app.services.github.client import GitHubClient
from app.workers.ingestion import run_sync

SyncRunner = Callable[[int], None]


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
