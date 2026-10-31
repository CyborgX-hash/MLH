"""Database fixtures. DB tests use a separate `<name>_test` database that is reset for every test.

Locally they are skipped when PostgreSQL is not reachable; with RUN_DB_TESTS=1 (CI) they must run.
"""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models import Base

_engine = None
ADMIN_TOKEN = "test-admin-token"
ADMIN = {"X-DeciTrace-Admin-Token": ADMIN_TOKEN}


@pytest.fixture(autouse=True)
def admin_token(monkeypatch):
    """Every test runs with an admin token configured; tests that need it disabled override the env."""
    monkeypatch.setenv("DECITRACE_ADMIN_TOKEN", ADMIN_TOKEN)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _test_engine():
    global _engine
    if _engine is not None:
        return _engine
    url = make_url(os.getenv("TEST_DATABASE_URL") or get_settings().database_url)
    test_url = url.set(database=f"{url.database}_test")
    try:
        admin = create_engine(url, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": test_url.database})
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{test_url.database}"'))
        admin.dispose()
        engine = create_engine(test_url)
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
    except OperationalError as exc:
        if os.getenv("RUN_DB_TESTS"):
            raise
        pytest.skip(f"PostgreSQL not available: {exc.__class__.__name__}")
    _engine = engine
    return engine


@pytest.fixture
def session_factory():
    engine = _test_engine()
    with engine.begin() as conn:
        names = ", ".join(t.name for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db(session_factory):
    with session_factory() as session:
        yield session
