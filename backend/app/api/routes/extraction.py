from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.models import ExtractionJob, Repository
from app.services.ai.client import AIClient
from app.services.extraction.extractor import run_extraction

router = APIRouter(tags=["extraction"])
ExtractionRunner = Callable[[int, int], None]


class ExtractionJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    model: str
    threads_total: int
    threads_done: int
    candidates: int
    created: int
    merged: int
    refused: int
    errors: List[Dict[str, Any]]
    created_at: datetime
    finished_at: Optional[datetime]


def extraction_model(settings: Settings) -> str:
    return settings.ai_extract_model or settings.ai_model


def get_extraction_runner(settings: Settings = Depends(get_settings)) -> ExtractionRunner:
    def runner(job_id: int, limit: int) -> None:
        def ai() -> AIClient:
            return AIClient(settings.ai_base_url, extraction_model(settings), settings.ai_api_key, None,
                            settings.ai_provider, settings.ai_timeout)
        run_extraction(job_id, SessionLocal, ai, limit)

    return runner


def _repo(db: Session, repository_id: int) -> Repository:
    repo = db.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found.")
    return repo


@router.post("/repositories/{repository_id}/extract", response_model=ExtractionJobOut, status_code=status.HTTP_202_ACCEPTED)
def start_extraction(
    repository_id: int,
    background: BackgroundTasks,
    limit: int = Query(5, ge=1, le=10, description="How many discussion threads to analyse"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    runner: ExtractionRunner = Depends(get_extraction_runner),
) -> ExtractionJobOut:
    """Ask the model for candidate decisions in the most-discussed threads. Every candidate is validated
    against stored evidence before anything is recorded."""
    _repo(db, repository_id)
    active = db.scalars(select(ExtractionJob).where(ExtractionJob.repository_id == repository_id,
                                                    ExtractionJob.status.in_(("queued", "running")))).first()
    if active:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Extraction job {active.id} is already {active.status}.")
    job = ExtractionJob(repository_id=repository_id, status="queued", model=extraction_model(settings), errors=[])
    db.add(job)
    db.commit()
    db.refresh(job)
    background.add_task(runner, job.id, limit)
    return job


@router.get("/repositories/{repository_id}/extraction-status", response_model=Optional[ExtractionJobOut])
def extraction_status(repository_id: int, db: Session = Depends(get_db)) -> Optional[ExtractionJob]:
    _repo(db, repository_id)
    return db.scalars(select(ExtractionJob).where(ExtractionJob.repository_id == repository_id)
                      .order_by(ExtractionJob.id.desc())).first()
