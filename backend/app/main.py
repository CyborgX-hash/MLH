import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.api.routes import ask, decisions, health, impact, links, repositories, views
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.workers.ingestion import fail_interrupted_jobs

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        with SessionLocal() as db:
            n = fail_interrupted_jobs(db)
            if n:
                log.warning("marked %d interrupted sync job(s) as failed", n)
    except SQLAlchemyError:
        log.warning("database unavailable at startup; /api/health will report it")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(repositories.router, prefix="/api")
    app.include_router(decisions.router, prefix="/api")
    app.include_router(links.router, prefix="/api")
    app.include_router(ask.router, prefix="/api")
    app.include_router(views.router, prefix="/api")
    app.include_router(impact.router, prefix="/api")
    return app


app = create_app()
