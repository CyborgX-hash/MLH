import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import app


class FakeResult:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row


class FakeSession:
    def __init__(self, vector=True, fail=False):
        self.vector, self.fail = vector, fail

    def execute(self, stmt):
        if self.fail:
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))
        return FakeResult((1,) if self.vector or "pg_extension" not in str(stmt) else None)


def client_with(session):
    app.dependency_overrides[get_db] = lambda: session
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_health_ok():
    r = client_with(FakeSession()).get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["database"] == {"reachable": True, "pgvector": True, "error": None}


def test_health_degraded_without_pgvector():
    r = client_with(FakeSession(vector=False)).get("/api/health")
    assert r.status_code == 503 and r.json()["database"]["pgvector"] is False


def test_health_degraded_when_database_down_without_leaking_details():
    r = client_with(FakeSession(fail=True)).get("/api/health")
    assert r.status_code == 503
    db = r.json()["database"]
    assert db["reachable"] is False and db["error"] == "OperationalError"
    assert "connection refused" not in r.text


@pytest.mark.skipif(not os.getenv("RUN_DB_TESTS"), reason="needs a running PostgreSQL with pgvector")
def test_health_against_real_database():
    r = TestClient(app).get("/api/health")
    assert r.status_code == 200, r.text
    assert r.json()["database"]["pgvector"] is True


@pytest.mark.parametrize("given,expected", [
    ("postgres://u:p@db.example.com:5432/app?sslmode=require",
     "postgresql+psycopg://u:p@db.example.com:5432/app?sslmode=require"),
    ("postgresql://u:p@ep-x.neon.tech/neondb?sslmode=require&channel_binding=require",
     "postgresql+psycopg://u:p@ep-x.neon.tech/neondb?sslmode=require&channel_binding=require"),
    ("postgresql+psycopg://u:p@localhost:5433/decitrace", "postgresql+psycopg://u:p@localhost:5433/decitrace"),
])
def test_hosted_database_urls_get_the_psycopg_driver(monkeypatch, given, expected):
    from app.core.config import Settings
    monkeypatch.setenv("DATABASE_URL", given)
    assert Settings().database_url == expected
