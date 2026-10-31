from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.core.config import Settings, get_settings
from app.models import Repository
from app.services.ai.client import AIClient, AIError
from app.services.retrieval.answer import Ask, answer_question
from app.services.retrieval.indexer import build_index

router = APIRouter(tags=["ask"])


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)


def get_ai_client(settings: Settings = Depends(get_settings)) -> Iterator[AIClient]:
    client = AIClient.from_settings(settings)
    try:
        yield client
    finally:
        client.close()


def _repo(db: Session, repository_id: int) -> Repository:
    repo = db.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found.")
    return repo


@router.post("/repositories/{repository_id}/ask", response_model=Ask)
def ask(repository_id: int, body: AskRequest, db: Session = Depends(get_db), ai: AIClient = Depends(get_ai_client)) -> Ask:
    repo = _repo(db, repository_id)
    try:
        return answer_question(db, repo, body.question.strip(), ai)
    except AIError as exc:
        raise HTTPException(exc.status, str(exc))


@router.post("/repositories/{repository_id}/index", dependencies=[Depends(require_admin)])
def rebuild_index(repository_id: int, db: Session = Depends(get_db), ai: AIClient = Depends(get_ai_client)) -> dict:
    """Rebuild the knowledge base (also runs automatically after each sync)."""
    return build_index(db, _repo(db, repository_id), ai)
