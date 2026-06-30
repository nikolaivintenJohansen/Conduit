import pytest
from fastapi.testclient import TestClient

from services.app.main import app
from services.shared.models import Wallet
from services.wallet.auth import create_user, issue_session
from services.wallet.deps import get_db
from services.wallet.ledger import debit_wallet


@pytest.fixture
def api_client(db_session, settings_env):
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
    user = create_user(db_session, "dashboard@example.com", "secure-pass-99")
    wallet = Wallet(user_id=user.id, balance_microdollars=2_000_000)
    db_session.add(wallet)
    db_session.flush()
    token = issue_session(db_session, user).jwt_token
    return {"Authorization": f"Bearer {token}"}


def test_dashboard_page_served(api_client):
    response = api_client.get("/dashboard")
    assert response.status_code == 200
    assert "Conduit" in response.text
    assert "/dashboard/app.js" in response.text


def test_dashboard_static_assets(api_client):
    js = api_client.get("/dashboard/app.js")
    css = api_client.get("/dashboard/styles.css")
    assert js.status_code == 200
    assert css.status_code == 200
    assert "loadDashboard" in js.text


def test_topup_result_pages(api_client):
    success = api_client.get("/wallet/topup/success")
    cancel = api_client.get("/wallet/topup/cancel")
    assert success.status_code == 200
    assert "Payment successful" in success.text
    assert cancel.status_code == 200
    assert "Payment cancelled" in cancel.text


def test_patch_wallet_settings_spend_limit(api_client, auth_headers, db_session):
    response = api_client.patch(
        "/wallet/v1/wallet/settings",
        headers=auth_headers,
        json={"spend_limit_microdollars": 5_000_000, "low_balance_threshold_microdollars": 500_000},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["spend_limit_microdollars"] == 5_000_000
    assert body["low_balance_threshold_microdollars"] == 500_000


def test_patch_wallet_settings_clear_spend_limit(api_client, auth_headers):
    api_client.patch(
        "/wallet/v1/wallet/settings",
        headers=auth_headers,
        json={"spend_limit_microdollars": 1_000_000},
    )
    response = api_client.patch(
        "/wallet/v1/wallet/settings",
        headers=auth_headers,
        json={"spend_limit_microdollars": None},
    )
    assert response.status_code == 200
    assert response.json()["spend_limit_microdollars"] is None


def test_wallet_includes_monthly_spend(api_client, auth_headers, db_session):
    wallet_response = api_client.get("/wallet/v1/wallet", headers=auth_headers)
    wallet_id = wallet_response.json()["wallet_id"]

    debit_wallet(
        db_session,
        wallet_id,
        250_000,
        idempotency_key="dashboard-monthly-spend",
    )

    response = api_client.get("/wallet/v1/wallet", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["monthly_spend_microdollars"] == 250_000
