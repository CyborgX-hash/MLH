"""API tests: FastAPI + PostgreSQL + mocked GitHub, background ingestion included."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db, get_github_client, get_sync_runner
from app.core.config import get_settings
from app.main import app
from app.workers.ingestion import Limits, run_sync
from tests.github_fake import O, R, FakeGitHub

URL = f"https://github.com/{O}/{R}"


@pytest.fixture
def fake():
    return FakeGitHub()


@pytest.fixture
def client(session_factory, fake):
    def db_override():
        with session_factory() as s:
            yield s

    limits = Limits.for_token(True)
    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_github_client] = lambda: fake.client()
    app.dependency_overrides[get_sync_runner] = lambda: (
        lambda job_id: run_sync(job_id, session_factory, lambda: fake.client(), limits)
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_connect_runs_ingestion_and_reports_progress(client):
    r = client.post("/api/repositories/connect", json={"url": URL})
    assert r.status_code == 201, r.text
    repo = r.json()
    assert repo["full_name"] == f"{O}/{R}" and repo["latest_job"]["status"] == "queued"

    # TestClient runs background tasks before returning, so ingestion has finished here.
    status = client.get(f"/api/repositories/{repo['id']}/sync-status").json()
    assert status["status"] == "completed" and status["stage_label"] == "Processing completed"
    detail = client.get(f"/api/repositories/{repo['id']}").json()
    assert detail["counts"] == {"issues": 2, "pull_requests": 1, "comments": 6, "discussions": 1,
                                "commits": 1, "source_files": 3}
    listing = client.get("/api/repositories").json()
    assert [x["id"] for x in listing] == [repo["id"]]


def test_reconnect_is_idempotent(client):
    first = client.post("/api/repositories/connect", json={"url": URL}).json()
    r = client.post("/api/repositories/connect", json={"url": URL + ".git"})
    assert r.status_code == 200 and r.json()["id"] == first["id"]
    assert len(client.get("/api/repositories").json()) == 1


@pytest.mark.parametrize("url", ["not a url", "https://gitlab.com/a/b", "https://github.com/orgs/psf"])
def test_invalid_url_is_422(client, url):
    r = client.post("/api/repositories/connect", json={"url": url})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)


def test_missing_or_deleted_repository_is_404(client):
    r = client.post("/api/repositories/connect", json={"url": "https://github.com/ghost/deleted-repo"})
    assert r.status_code == 404 and "deleted" in r.json()["detail"]


def test_private_repository_is_rejected(client, fake):
    fake.repo.update(private=True, visibility="private")
    assert client.post("/api/repositories/connect", json={"url": URL}).status_code == 403


def test_rate_limit_is_429_and_never_leaks_token(client, fake):
    fake.fail[f"/repos/{O}/{R}"] = lambda: httpx.Response(
        403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "9999999999"}, json={})
    r = client.post("/api/repositories/connect", json={"url": URL})
    assert r.status_code == 429 and "Retry-After" in r.headers
    assert "test-token" not in r.text


def test_github_outage_is_502(client, fake):
    fake.fail[f"/repos/{O}/{R}"] = lambda: httpx.Response(503)
    assert client.post("/api/repositories/connect", json={"url": URL}).status_code == 502


def test_manual_sync_and_conflict(client, session_factory):
    repo = client.post("/api/repositories/connect", json={"url": URL}).json()
    r = client.post(f"/api/repositories/{repo['id']}/sync?full=true")
    assert r.status_code == 202 and r.json()["full"] is True

    # A job that is still running blocks a second one.
    from app.models import SyncJob
    with session_factory() as s:
        s.add(SyncJob(repository_id=repo["id"], status="running", stage="issues", progress={}, errors=[]))
        s.commit()
    assert client.post(f"/api/repositories/{repo['id']}/sync").status_code == 409


def test_unknown_repository_is_404(client):
    assert client.get("/api/repositories/999").status_code == 404
    assert client.post("/api/repositories/999/sync").status_code == 404
    assert client.get("/api/repositories/999/sync-status").status_code == 404


def test_health_never_exposes_token(client, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_supersecret")
    get_settings.cache_clear()
    try:
        r = client.get("/api/health")
        assert r.json()["github_token_configured"] is True
        assert "ghp_supersecret" not in r.text
    finally:
        get_settings.cache_clear()
