"""Integration tests for POST /v1/authorize (Phase 4 fast path)."""

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


def test_authorize_returns_200_with_fast_hold(
    api_client, db_session, sandbox_user, sandbox_wallet, sandbox_key, model_catalog
):
    _vkey, plaintext = sandbox_key
    response = api_client.post(
        "/v1/authorize",
        headers={"Authorization": f"Bearer {plaintext}", "X-Request-Id": "req-auth-1"},
        json={"model": "gpt-4o-mini"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["authorized"] is True
    assert body["mode"] == "fast"
    assert body["request_id"] == "req-auth-1"
    assert body["held_microdollars"] >= 100_000


def test_authorize_402_when_insufficient_balance(
    api_client, db_session, sandbox_user, model_catalog
):
    from services.shared.models import Wallet

    db_session.add(Wallet(user_id=sandbox_user.id, balance_microdollars=50_000))
    db_session.flush()

    from services.shared.models import VirtualKey
    from services.wallet.keys import generate_virtual_key

    generated = generate_virtual_key()
    db_session.add(
        VirtualKey(
            user_id=sandbox_user.id,
            name="vk",
            key_prefix=generated.prefix,
            key_hash=generated.key_hash,
        )
    )
    db_session.flush()

    response = api_client.post(
        "/v1/authorize",
        headers={"Authorization": f"Bearer {generated.plaintext}"},
        json={"model": "gpt-4o"},
    )
    assert response.status_code == 402
    assert response.json()["detail"]["error"]["code"] == "insufficient_balance"


def test_authorize_with_app_token_enforces_allowance(
    api_client, db_session, sandbox_user, sandbox_wallet, app_registration, model_catalog
):
    from services.wallet.apps import connect_app

    install = connect_app(
        db_session,
        user_id=sandbox_user.id,
        client_id=app_registration.client_id,
        spend_limit_microdollars=50_000,
    )
    from services.wallet.oauth import create_authorization_code, exchange_code_for_tokens

    code = create_authorization_code(
        db_session,
        client_id=app_registration.client_id,
        user_id=sandbox_user.id,
        app_install_id=install.id,
        redirect_uri="https://delegated.example.com/cb",
    )
    tokens = exchange_code_for_tokens(
        db_session,
        code=code.code,
        code_verifier=None,
        client_id=app_registration.client_id,
        client_secret=None,
        redirect_uri="https://delegated.example.com/cb",
    )

    response = api_client.post(
        "/v1/authorize",
        headers={"Authorization": f"Bearer {tokens.access_token}"},
        json={"model": "gpt-4o-mini"},
    )
    assert response.status_code == 402
    assert response.json()["detail"]["error"]["code"] == "allowance_exceeded"


def test_authorize_requires_auth(api_client):
    response = api_client.post("/v1/authorize", json={"model": "gpt-4o-mini"})
    assert response.status_code == 401


def test_authorize_402_when_monthly_spend_limit_exceeded(
    api_client, db_session, sandbox_user, model_catalog
):
    from services.shared.models import VirtualKey, Wallet
    from services.wallet.keys import generate_virtual_key

    db_session.add(
        Wallet(
            user_id=sandbox_user.id,
            balance_microdollars=5_000_000,
            spend_limit_microdollars=50_000,  # below the $0.10 minimum hold
        )
    )
    db_session.flush()

    generated = generate_virtual_key()
    db_session.add(
        VirtualKey(
            user_id=sandbox_user.id,
            name="vk",
            key_prefix=generated.prefix,
            key_hash=generated.key_hash,
        )
    )
    db_session.flush()

    response = api_client.post(
        "/v1/authorize",
        headers={"Authorization": f"Bearer {generated.plaintext}"},
        json={"model": "gpt-4o-mini"},
    )
    assert response.status_code == 402
    assert response.json()["detail"]["error"]["code"] == "spend_limit_exceeded"
