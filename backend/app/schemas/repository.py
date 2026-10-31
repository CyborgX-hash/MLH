from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ConnectRequest(BaseModel):
    url: str = Field(..., max_length=300, examples=["https://github.com/psf/requests"])


class SyncJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    stage: str
    stage_label: str = ""
    full: bool
    progress: Dict[str, Any]
    errors: List[Dict[str, Any]]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]


class RepositoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner: str
    name: str
    full_name: str
    html_url: str
    description: Optional[str]
    default_branch: str
    language: Optional[str]
    license_spdx: Optional[str]
    stars: int
    archived: bool
    has_discussions: bool
    connected_at: datetime
    last_synced_at: Optional[datetime]
    latest_job: Optional[SyncJobOut] = None
    stats: Optional[Dict[str, Any]] = None


class RepositoryCounts(BaseModel):
    issues: int
    pull_requests: int
    comments: int
    discussions: int
    commits: int
    source_files: int


class RepositoryDetail(RepositoryOut):
    counts: RepositoryCounts
