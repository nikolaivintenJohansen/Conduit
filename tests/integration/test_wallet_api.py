import pytest
from fastapi.testclient import TestClient

from services.app.main import app
from services.shared.models import Wallet
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
    user = create_user(db_session, "wallet-api@example.com", "secure-pass-99")
    wallet = Wallet(user_id=user.id, balance_microdollars=2_000_000)
    db_session.add(wallet)
    db_session.flush()

    credit_wallet(
        db_session,
        wallet.id,
        1_000_000,
        idempotency_key="api-test-credit",
    )

    token = issue_session(db_session, user).jwt_token
    return {"Authorization": f"Bearer {token}"}


def test_get_wallet_requires_auth(api_client):
    response = api_client.get("/wallet/v1/wallet")
    assert response.status_code == 401


def test_get_wallet_balance(api_client, auth_headers, db_session):
    response = api_client.get("/wallet/v1/wallet", headers=auth_headers)
    assert response.status_code == 200

    body = response.json()
    assert body["currency"] == "USD"
    assert body["balance_microdollars"] == 3_000_000
    assert body["available_microdollars"] == 3_000_000
    assert "wallet_id" in body


def test_list_transactions(api_client, auth_headers):
    response = api_client.get("/wallet/v1/wallet/transactions", headers=auth_headers)
    assert response.status_code == 200

    body = response.json()
    assert "data" in body
    assert len(body["data"]) >= 1
    assert body["data"][0]["entry_type"] in {
        "credit",
        "debit",
        "hold",
        "hold_release",
        "refund",
        "adjustment",
    }
