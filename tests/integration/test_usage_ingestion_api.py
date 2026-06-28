"""Integration tests for POST /v1/usage (Phase 4 ingestion)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.app.main import app
from services.gateway import balance_cache, usage_queue
from services.gateway.allowance_cache import reset_allowance_cache
from services.gateway.rate_limit import reset_rate_limit_state
from services.wallet.deps import get_db


@pytest.fixture
def api_client(db_session, settings_env):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    reset_rate_limit_state()
    reset_allowance_cache()
    balance_cache.reset_balance_cache()
    usage_queue.reset_usage_queue()
    usage_queue.reset_idempotency()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    reset_rate_limit_state()
    reset_allowance_cache()
    balance_cache.reset_balance_cache()
    usage_queue.reset_usage_queue()
    usage_queue.reset_idempotency()


def test_usage_ingest_returns_202_and_enqueues(
    api_client, db_session, sandbox_user, sandbox_wallet, sandbox_key, model_catalog
):
    _vkey, plaintext = sandbox_key

    # Authorize first so a hold exists (the usage event references the hold).
    auth = api_client.post(
        "/v1/authorize",
        headers={"Authorization": f"Bearer {plaintext}", "X-Request-Id": "req-ingest-1"},
        json={"model": "gpt-4o-mini"},
    )
    assert auth.status_code == 200
    held = auth.json()["held_microdollars"]

    response = api_client.post(
        "/v1/usage",
        headers={"Authorization": f"Bearer {plaintext}"},
        json={
            "events": [
                {
                    "request_id": "req-ingest-1",
                    "model": "gpt-4o-mini",
                    "input_tokens": 120,
                    "output_tokens": 80,
                }
            ]
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["accepted"] == 1
    assert body["duplicated"] == 0
    assert body["request_ids"] == ["req-ingest-1"]
    assert usage_queue.stream_length() == 1

    # The enqueued event should carry the hold estimate so the worker can release it.
    usage_queue.ensure_consumer_group()
    batch = usage_queue.read_batch(consumer="test", count=10, block_ms=0)
    fields = batch[0][1]
    assert fields["request_id"] == "req-ingest-1"
    assert int(fields["estimated_max_microdollars"]) == held


def test_usage_ingest_is_idempotent(
    api_client, db_session, sandbox_user, sandbox_wallet, sandbox_key, model_catalog
):
    _vkey, plaintext = sandbox_key
    payload = {
        "events": [
            {
                "request_id": "req-dup-1",
                "model": "gpt-4o-mini",
                "input_tokens": 10,
                "output_tokens": 5,
            }
        ]
    }
    first = api_client.post(
        "/v1/usage", headers={"Authorization": f"Bearer {plaintext}"}, json=payload
    )
    assert first.json()["accepted"] == 1

    second = api_client.post(
        "/v1/usage", headers={"Authorization": f"Bearer {plaintext}"}, json=payload
    )
    assert second.status_code == 202
    assert second.json()["accepted"] == 0
    assert second.json()["duplicated"] == 1


def test_usage_ingest_rejects_empty_events(
    api_client, db_session, sandbox_user, sandbox_wallet, sandbox_key
):
    _vkey, plaintext = sandbox_key
    response = api_client.post(
        "/v1/usage",
        headers={"Authorization": f"Bearer {plaintext}"},
        json={"events": []},
    )
    assert response.status_code == 400


def test_usage_ingest_requires_auth(api_client):
    response = api_client.post(
        "/v1/usage", json={"events": [{"request_id": "x", "model": "gpt-4o-mini"}]}
    )
    assert response.status_code == 401
