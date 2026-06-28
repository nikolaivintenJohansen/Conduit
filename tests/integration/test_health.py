import os

import pytest
from httpx import ASGITransport, AsyncClient

from services.app.main import app


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code in {200, 503}
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert "database" in body
    assert "redis" in body


@pytest.mark.skipif(
    os.environ.get("TEST_DATABASE_URL") is None,
    reason="Set TEST_DATABASE_URL for live DB health check",
)
@pytest.mark.asyncio
async def test_health_with_database(live_services_env):
    from services.shared.db import dispose_engine

    await dispose_engine()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    body = response.json()
    assert response.status_code == 200, body
    assert body["database"] == "ok"
    assert body["redis"] == "ok"


@pytest.fixture
def live_services_env(monkeypatch: pytest.MonkeyPatch):
    from services.shared.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv(
        "DATABASE_URL",
        os.environ.get("DATABASE_URL", "postgresql://uaw:uaw@localhost:5432/uaw_test"),
    )
    monkeypatch.setenv(
        "REDIS_URL",
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    )
    yield
    get_settings.cache_clear()
