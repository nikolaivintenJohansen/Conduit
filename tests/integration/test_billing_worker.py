"""End-to-end billing worker tests: authorize → ingest → worker settles the ledger."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.app.main import app
from services.gateway import balance_cache, usage_queue, worker
from services.gateway.allowance_cache import reset_allowance_cache
from services.gateway.rate_limit import reset_rate_limit_state
from services.shared.models import UsageEvent, Wallet
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


def _authorize_and_ingest(api_client, token, request_id, model="gpt-4o-mini"):
    auth = api_client.post(
        "/v1/authorize",
        headers={"Authorization": f"Bearer {token}", "X-Request-Id": request_id},
        json={"model": model},
    )
    assert auth.status_code == 200, auth.text
    held = auth.json()["held_microdollars"]

    ingest = api_client.post(
        "/v1/usage",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "events": [
                {
                    "request_id": request_id,
                    "model": model,
                    "input_tokens": 120,
                    "output_tokens": 80,
                }
            ]
        },
    )
    assert ingest.status_code == 202, ingest.text
    return held


def test_worker_settles_fast_path_event(
    api_client, db_session, sandbox_user, sandbox_wallet, sandbox_key, model_catalog
):
    _vkey, plaintext = sandbox_key
    _authorize_and_ingest(api_client, plaintext, "req-worker-1")

    stats = worker.run_once(session=db_session)
    assert stats.settled == 1
    assert stats.failed == 0

    # Ledger debited.
    wallet = db_session.query(Wallet).filter_by(user_id=sandbox_user.id).one()
    assert wallet.balance_microdollars < 5_000_000
    assert wallet.held_microdollars == 0  # no DB hold on the fast path

    # Usage event recorded.
    events = db_session.query(UsageEvent).filter_by(user_id=sandbox_user.id).all()
    assert len(events) == 1
    assert events[0].request_id == "req-worker-1"
    assert events[0].charged_microdollars > 0

    # Redis-side hold released.
    assert balance_cache.get_hold("req-worker-1") is None
    cached = balance_cache.get_balance_state(wallet.id)
    assert cached is not None
    assert cached["held_microdollars"] == 0
    assert cached["balance_microdollars"] == wallet.balance_microdollars

    # Stream drained + acked.
    assert usage_queue.pending_count() == 0
    assert usage_queue.stream_length() == 0


def test_worker_is_idempotent_under_redelivery(
    api_client, db_session, sandbox_user, sandbox_wallet, sandbox_key, model_catalog
):
    _vkey, plaintext = sandbox_key
    _authorize_and_ingest(api_client, plaintext, "req-worker-2")

    worker.run_once(session=db_session)
    # Re-enqueue the same request_id (simulating a redelivery) and drain again.
    usage_queue.enqueue_event(
        {
            "request_id": "req-worker-2",
            "user_id": str(sandbox_user.id),
            "wallet_id": str(sandbox_wallet.id),
            "model": "gpt-4o-mini",
            "input_tokens": 120,
            "output_tokens": 80,
        }
    )
    stats = worker.run_once(session=db_session)
    assert stats.settled == 0
    assert stats.skipped == 1

    # Still exactly one usage event / one debit.
    events = db_session.query(UsageEvent).filter_by(user_id=sandbox_user.id).all()
    assert len(events) == 1


def test_worker_settles_app_scoped_event_and_increments_allowance(
    api_client,
    db_session,
    sandbox_user,
    sandbox_wallet,
    app_registration,
    connected_app,
    app_access_token,
    model_catalog,
):
    _authorize_and_ingest(api_client, app_access_token, "req-worker-app-1")

    stats = worker.run_once(session=db_session)
    assert stats.settled == 1
    assert stats.failed == 0

    events = db_session.query(UsageEvent).filter_by(user_id=sandbox_user.id).all()
    assert len(events) == 1
    assert events[0].metadata_json.get("app_install_id") == str(connected_app.id)

    db_session.refresh(connected_app)
    assert connected_app.allowance_spent_microdollars == events[0].charged_microdollars

    from services.gateway.allowance_cache import get_allowance_state

    state = get_allowance_state(connected_app.id)
    assert state is not None
    assert state["allowance_spent_microdollars"] == events[0].charged_microdollars


def test_worker_handles_empty_queue(db_session):
    usage_queue.reset_usage_queue()
    stats = worker.run_once(session=db_session)
    assert stats.processed == 0


def test_worker_increments_redis_monthly_spent(
    api_client, db_session, sandbox_user, sandbox_wallet, sandbox_key, model_catalog
):
    _vkey, plaintext = sandbox_key
    _authorize_and_ingest(api_client, plaintext, "req-monthly-1")

    stats = worker.run_once(session=db_session)
    assert stats.settled == 1

    events = db_session.query(UsageEvent).filter_by(user_id=sandbox_user.id).all()
    charged = events[0].charged_microdollars
    assert charged > 0

    cached = balance_cache.get_balance_state(sandbox_wallet.id)
    assert cached is not None
    assert cached["monthly_spent_microdollars"] == charged


def test_worker_moves_poison_event_to_dlq(db_session, settings_env):
    from uuid import uuid4

    from services.shared.config import get_settings

    usage_queue.reset_usage_queue()
    usage_queue.reset_idempotency()

    # Poison payload: input_tokens is non-numeric → settle_event raises ValueError.
    usage_queue.enqueue_event(
        {
            "request_id": "req-poison-1",
            "user_id": str(uuid4()),
            "wallet_id": str(uuid4()),
            "model": "gpt-4o-mini",
            "input_tokens": "not-an-int",
            "output_tokens": 80,
        }
    )

    max_attempts = get_settings().worker_max_delivery_attempts
    # First `max_attempts` runs fail and leave the entry un-acked for retry; the
    # next run exceeds the cap and moves it to the DLQ. ``claim_idle_ms=0``
    # forces immediate re-delivery of the un-acked entry (real Redis only
    # re-delivers pending entries via XCLAIM).
    for _ in range(max_attempts + 1):
        stats = worker.run_once(session=db_session, claim_idle_ms=0)
        assert stats.failed == 1

    assert usage_queue.dlq_length() == 1
    assert usage_queue.pending_count() == 0

    dlq_entries = usage_queue.read_dlq()
    assert len(dlq_entries) == 1
    assert dlq_entries[0][1]["reason"] == "max_delivery_attempts"
    assert dlq_entries[0][1]["request_id"] == "req-poison-1"
