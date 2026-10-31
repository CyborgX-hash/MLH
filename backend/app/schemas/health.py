from typing import Literal, Optional

from pydantic import BaseModel


class DatabaseHealth(BaseModel):
    reachable: bool
    pgvector: bool
    error: Optional[str] = None


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    app: str
    version: str
    environment: str
    database: DatabaseHealth
    # Only whether a token is set; the token itself is never sent to clients.
    github_token_configured: bool
