from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.health import DatabaseHealth, Health

router = APIRouter(tags=["health"])


def check_database(db: Session) -> DatabaseHealth:
    try:
        db.execute(text("SELECT 1"))
        has_vector = db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).first() is not None
        return DatabaseHealth(reachable=True, pgvector=has_vector)
    except SQLAlchemyError as exc:
        return DatabaseHealth(reachable=False, pgvector=False, error=exc.__class__.__name__)


@router.get("/health", response_model=Health)
def health(response: Response, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> Health:
    database = check_database(db)
    ok = database.reachable and database.pgvector
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Health(
        status="ok" if ok else "degraded",
        app=settings.app_name,
        version=__version__,
        environment=settings.environment,
        database=database,
        github_token_configured=bool(settings.github_token),
    )
