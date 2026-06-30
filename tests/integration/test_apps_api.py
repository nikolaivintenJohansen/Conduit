import pytest
from fastapi.testclient import TestClient

from services.app.main import app
from services.shared.models import AppRegistration, PartnerAccount
from services.wallet.auth import create_user, issue_session
from services.wallet.deps import get_db


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
def user_and_app(db_session):
    from uuid import uuid4

    user = create_user(db_session, f"apps-{uuid4()}@example.com", "super-password-1")
    partner = PartnerAccount(name="P", slug=f"p-{uuid4().hex[:8]}")
    db_session.add(partner)
    db_session.flush()
    reg = AppRegistration(
        partner_account_id=partner.id,
        name="DemoApp",
        client_id=f"conduit_{uuid4().hex}",
        client_secret_hash="hash",
        redirect_uris=["https://demo.example.com/cb"],
    )
    db_session.add(reg)
    db_session.flush()
    token = issue_session(db_session, user).jwt_token
    return user, reg, token


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_connect_list_update_revoke_flow(api_client, db_session, user_and_app):
    user, reg, token = user_and_app
    headers = _headers(token)

    connect = api_client.post(
        f"/wallet/v1/apps/{reg.client_id}/connect",
        headers=headers,
        json={"spend_limit_microdollars": 5_000_000, "reset_period": "monthly"},
    )
    assert connect.status_code == 201
    install_id = connect.json()["install_id"]
    assert connect.json()["spend_limit_microdollars"] == 5_000_000
    assert connect.json()["app_name"] == "DemoApp"

    listed = api_client.get("/wallet/v1/apps", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1
    assert listed.json()["data"][0]["install_id"] == install_id

    updated = api_client.patch(
        f"/wallet/v1/apps/{install_id}",
        headers=headers,
        json={"spend_limit_microdollars": 10_000_000},
    )
    assert updated.status_code == 200
    assert updated.json()["spend_limit_microdollars"] == 10_000_000

    revoked = api_client.delete(f"/wallet/v1/apps/{install_id}", headers=headers)
    assert revoked.status_code == 204

    fetched = api_client.get(f"/wallet/v1/apps/{install_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["revoked_at"] is not None


def test_connect_unknown_app_404(api_client, user_and_app):
    _, _, token = user_and_app
    response = api_client.post(
        "/wallet/v1/apps/conduit_unknown/connect",
        headers=_headers(token),
        json={"spend_limit_microdollars": 1_000_000},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "app_not_found"


def test_apps_routes_require_auth(api_client):
    assert api_client.get("/wallet/v1/apps").status_code == 401
