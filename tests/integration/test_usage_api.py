import pytest
from fastapi.testclient import TestClient

from services.app.main import app
from services.shared.models import UsageEvent, Wallet
from services.wallet.auth import create_user, issue_session
from services.wallet.ledger import credit_wallet


@pytest.fixture
def api_client(db_session, settings_env):
    from services.wallet.deps import get_db

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(db_session, settings_env) -> dict[str, str]:
    user = create_user(db_session, "usage-api@example.com", "secure-pass-99")
    wallet = Wallet(user_id=user.id, balance_microdollars=2_000_000)
    db_session.add(wallet)
    db_session.flush()

    credit_wallet(
        db_session,
        wallet.id,
        1_000_000,
        idempotency_key="usage-api-credit",
    )

    token = issue_session(db_session, user).jwt_token
    return {"Authorization": f"Bearer {token}"}


def test_list_usage_requires_auth(api_client):
    response = api_client.get("/wallet/v1/usage")
    assert response.status_code == 401


def test_list_usage_empty(api_client, auth_headers):
    response = api_client.get("/wallet/v1/usage", headers=auth_headers)
    assert response.status_code == 200

    body = response.json()
    assert body["data"] == []
    assert body["next_cursor"] is None


def test_list_usage_after_gateway_call(
    api_client, db_session, sandbox_user, sandbox_key, model_catalog, settings_env
):
    from services.shared.models import Wallet

    vkey, plaintext = sandbox_key
    wallet = Wallet(user_id=sandbox_user.id, balance_microdollars=5_000_000)
    db_session.add(wallet)
    db_session.flush()

    auth_headers = {"Authorization": f"Bearer {issue_session(db_session, sandbox_user).jwt_token}"}

    gateway_response = api_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {plaintext}"},
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "usage api test"}],
        },
    )
    assert gateway_response.status_code == 200

    usage_response = api_client.get("/wallet/v1/usage", headers=auth_headers)
    assert usage_response.status_code == 200

    events = usage_response.json()["data"]
    assert len(events) >= 1
    assert events[0]["model"] == "gpt-4o-mini"
    assert events[0]["charged_microdollars"] > 0
    assert db_session.query(UsageEvent).filter_by(user_id=sandbox_user.id).count() == 1
