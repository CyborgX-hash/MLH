from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_github_client
from app.api.routes.repositories import _github_http_error
from app.models import Decision, Repository
from app.services.github.client import GitHubClient
from app.services.github.errors import GitHubError
from app.services.github.urls import parse_pr_url
from app.services.impact.code_map import map_decision
from app.services.impact.pr_impact import NOTE, analyze, supporting_sources

router = APIRouter(tags=["pr-impact"])


class ImpactRequest(BaseModel):
    pr_url: str = Field(..., max_length=300, examples=["https://github.com/psf/requests/pull/7272"])


class ChangedFile(BaseModel):
    filename: str
    status: str
    previous_filename: Optional[str] = None
    additions: int = 0
    deletions: int = 0


class Trigger(BaseModel):
    signal: str
    detail: str
    file: str
    lines: List[str]


class Source(BaseModel):
    url: str
    author: Optional[str]
    claim_type: str
    quote: str
    verification_state: str


class ImpactFinding(BaseModel):
    decision_id: int
    topic: str
    decision: Optional[str]
    status: str
    determination: str
    severity: str  # potential_conflict | related
    headline: str
    triggers: List[Trigger]
    triggered_by_files: List[str]
    supporting_sources: List[Source]


class PullRequestInfo(BaseModel):
    number: int
    title: str
    url: str
    state: str
    merged: bool
    author: Optional[str]


class ImpactReport(BaseModel):
    repository_id: int
    pull_request: PullRequestInfo
    changed_files: List[ChangedFile]
    findings: List[ImpactFinding]
    note: str
    decisions_checked: int


@router.post("/pr-impact", response_model=ImpactReport)
def pr_impact(body: ImpactRequest, db: Session = Depends(get_db), gh: GitHubClient = Depends(get_github_client)) -> ImpactReport:
    try:
        owner, name, number = parse_pr_url(body.pr_url)
    except GitHubError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    repo = db.scalars(select(Repository).where(func.lower(Repository.full_name) == f"{owner}/{name}".lower())).first()
    if repo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            f"github.com/{owner}/{name} is not connected to DeciTrace. Connect it first so its history can be checked.")
    try:
        pr = gh.get_pull_request(repo.owner, repo.name, number)
        files = list(gh.get_pull_request_files(repo.owner, repo.name, number))
    except GitHubError as exc:
        err = _github_http_error(exc, owner, name)
        if err.status_code == 404:
            err.detail = f"Pull request #{number} was not found in {repo.full_name}."
        raise err

    decisions = db.scalars(select(Decision).where(Decision.repository_id == repo.id, Decision.status != "superseded")).all()
    for d in decisions:  # code links reflect the latest sync
        map_decision(db, d)
    findings = analyze(db, repo, files)

    def headline(sev: str) -> str:
        return "Potential conflict with historical decision" if sev == "potential_conflict" else "Touches code linked to a historical decision"

    return ImpactReport(
        repository_id=repo.id,
        pull_request=PullRequestInfo(number=pr["number"], title=pr.get("title", ""), url=pr["html_url"],
                                     state=pr.get("state", ""), merged=bool(pr.get("merged_at")),
                                     author=(pr.get("user") or {}).get("login")),
        changed_files=[ChangedFile(filename=f["filename"], status=f.get("status", ""), previous_filename=f.get("previous_filename"),
                                   additions=f.get("additions", 0), deletions=f.get("deletions", 0)) for f in files],
        findings=[ImpactFinding(
            decision_id=fd.decision.id, topic=fd.decision.topic, decision=fd.decision.decision, status=fd.decision.status,
            determination=fd.decision.determination, severity=fd.severity, headline=headline(fd.severity),
            triggers=[Trigger(signal=h.signal, detail=h.detail, file=h.file, lines=h.lines) for h in fd.hits],
            triggered_by_files=sorted({h.file for h in fd.hits}),
            supporting_sources=[Source(**s) for s in supporting_sources(db, fd.decision)],
        ) for fd in findings],
        note=NOTE,
        decisions_checked=len(decisions),
    )
