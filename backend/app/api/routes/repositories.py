from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import SyncRunner, get_db, get_github_client, get_sync_runner
from app.db.upsert import upsert
from app.models import Comment, Commit, Discussion, Issue, PullRequest, Repository, SourceFile, SyncJob
from app.schemas.repository import ConnectRequest, RepositoryCounts, RepositoryDetail, RepositoryOut, SyncJobOut
from app.services.github.client import GitHubClient
from app.services.github.errors import GitHubError, NotFound, RateLimited
from app.services.github.urls import parse_repo_url
from app.workers.ingestion import STAGE_LABELS, repository_fields, start_job

router = APIRouter(prefix="/repositories", tags=["repositories"])


def _job_out(job: Optional[SyncJob]) -> Optional[SyncJobOut]:
    if job is None:
        return None
    out = SyncJobOut.model_validate(job)
    out.stage_label = STAGE_LABELS.get(job.stage, job.stage)
    return out


def _latest_job(db: Session, repo_id: int) -> Optional[SyncJob]:
    return db.scalars(select(SyncJob).where(SyncJob.repository_id == repo_id).order_by(SyncJob.id.desc())).first()


def _get_repo(db: Session, repository_id: int) -> Repository:
    repo = db.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found.")
    return repo


def _detail(db: Session, repo: Repository) -> RepositoryDetail:
    def count(model, *where) -> int:
        return db.scalar(select(func.count()).select_from(model).where(model.repository_id == repo.id, *where)) or 0

    out = RepositoryOut.model_validate(repo).model_dump()
    out["latest_job"] = _job_out(_latest_job(db, repo.id))
    return RepositoryDetail(
        **out,
        counts=RepositoryCounts(
            issues=count(Issue), pull_requests=count(PullRequest), comments=count(Comment),
            discussions=count(Discussion), commits=count(Commit), source_files=count(SourceFile),
        ),
    )


def _github_http_error(exc: GitHubError, owner: str, name: str) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"github.com/{owner}/{name} was not found. It may have been deleted or renamed, or it is private.",
        )
    if isinstance(exc, RateLimited):
        headers = {"Retry-After": "60"}
        return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc), headers=headers)
    code = exc.status if exc.status in (401, 403, 451) else status.HTTP_502_BAD_GATEWAY
    return HTTPException(code, str(exc))


@router.post("/connect", response_model=RepositoryDetail)
def connect_repository(
    body: ConnectRequest,
    background: BackgroundTasks,
    response: Response,
    db: Session = Depends(get_db),
    gh: GitHubClient = Depends(get_github_client),
    runner: SyncRunner = Depends(get_sync_runner),
) -> RepositoryDetail:
    try:
        owner, name = parse_repo_url(body.url)
    except GitHubError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    try:
        data = gh.get_repository(owner, name)
    except GitHubError as exc:
        raise _github_http_error(exc, owner, name)
    if data.get("private") or data.get("visibility", "public") != "public":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only public repositories are supported.")

    fields = repository_fields(data)
    existed = db.scalar(select(Repository.id).where(Repository.github_id == fields["github_id"])) is not None
    upsert(db, Repository, [{**fields, "sync_cursors": {}}], ["github_id"], update=list(fields))
    db.commit()
    repo = db.scalars(select(Repository).where(Repository.github_id == fields["github_id"])).one()

    job, created = start_job(db, repo)
    if created:
        background.add_task(runner, job.id)
    response.status_code = status.HTTP_200_OK if existed else status.HTTP_201_CREATED
    return _detail(db, repo)


@router.get("", response_model=List[RepositoryOut])
def list_repositories(db: Session = Depends(get_db)) -> List[RepositoryOut]:
    out = []
    for repo in db.scalars(select(Repository).order_by(Repository.connected_at.desc())):
        item = RepositoryOut.model_validate(repo)
        item.latest_job = _job_out(_latest_job(db, repo.id))
        out.append(item)
    return out


@router.get("/{repository_id}", response_model=RepositoryDetail)
def get_repository(repository_id: int, db: Session = Depends(get_db)) -> RepositoryDetail:
    return _detail(db, _get_repo(db, repository_id))


@router.post("/{repository_id}/sync", response_model=SyncJobOut, status_code=status.HTTP_202_ACCEPTED)
def sync_repository(
    repository_id: int,
    background: BackgroundTasks,
    full: bool = False,
    db: Session = Depends(get_db),
    runner: SyncRunner = Depends(get_sync_runner),
) -> SyncJobOut:
    repo = _get_repo(db, repository_id)
    job, created = start_job(db, repo, full=full)
    if not created:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Sync job {job.id} is already {job.status}.")
    background.add_task(runner, job.id)
    return _job_out(job)


@router.get("/{repository_id}/sync-status", response_model=SyncJobOut)
def sync_status(repository_id: int, db: Session = Depends(get_db)) -> SyncJobOut:
    _get_repo(db, repository_id)
    job = _latest_job(db, repository_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This repository has never been synced.")
    return _job_out(job)
