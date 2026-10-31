from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class RecordRef(BaseModel):
    kind: str
    id: int


class LinkOut(BaseModel):
    source: RecordRef
    target: RecordRef
    relation: str
    signal: str
    verification_status: str
    confidence: float
    evidence: Dict[str, Any]


class RecordOut(BaseModel):
    kind: str
    id: int
    number: Optional[int] = None
    title: Optional[str] = None
    url: Optional[str] = None
    state: Optional[str] = None
    sha: Optional[str] = None
    cited: bool = False
    missing: bool = False


class RelatedGraph(BaseModel):
    records: List[RecordOut]
    links: List[LinkOut]


class CodeLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    link_status: str
    basis: str
    pr_number: Optional[int]
    pr_url: Optional[str]
    merged_at: Optional[datetime]
    commit_sha: Optional[str]
    commit_url: Optional[str]
    path: Optional[str]
    change_type: Optional[str]
    current_path: Optional[str]
    deleted: bool
    changed_after: List[int]


class CodeMap(BaseModel):
    decision_id: int
    message: Optional[str]
    verified: List[CodeLinkOut]
    possible: List[CodeLinkOut]
    notes: List[str]


class FileDecision(BaseModel):
    decision_id: int
    topic: str
    status: str
    determination: str
    link_status: str
    pr_number: Optional[int]
    pr_url: Optional[str]
    path: Optional[str]
    current_path: Optional[str]
