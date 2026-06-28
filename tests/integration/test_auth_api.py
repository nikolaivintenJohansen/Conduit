import pytest
from fastapi.testclient import TestClient

from services.app.main import app
from services.wallet.auth import create_user, issue_session
from services.wallet.deps import get_db
from services.wallet.keys import KEY_PREFIX, resolve_virtual_key
from services.wallet.ledger import get_or_create_wallet


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


def _register_user(client: TestClient, email: str, password: str = "secure-pass-99") -> dict:
    response = client.post(
        "/wallet/v1/auth/register",
        json={"email": email, "password": password, "display_name": "Test User"},
    )
    assert response.status_code == 201
    return response.json()


def test_register_and_login(api_client):
    email = "register-login@example.com"

    register_body = _register_user(api_client, email)
    assert register_body["token_type"] == "bearer"
    assert register_body["access_token"]
    assert register_body["user"]["email"] == email
    assert register_body["expires_in"] > 0

    login_response = api_client.post(
        "/wallet/v1/auth/login",
        json={"email": email, "password": "secure-pass-99"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["access_token"]


def test_register_duplicate_email(api_client):
    email = "duplicate@example.com"
    _register_user(api_client, email)

    response = api_client.post(
        "/wallet/v1/auth/register",
        json={"email": email, "password": "secure-pass-99"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "email_taken"


def test_login_invalid_credentials(api_client):
    _register_user(api_client, "valid-user@example.com")

    response = api_client.post(
        "/wallet/v1/auth/login",
        json={"email": "valid-user@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "invalid_credentials"


def test_logout_invalidates_session(api_client):
    body = _register_user(api_client, "logout@example.com")
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    logout_response = api_client.post("/wallet/v1/auth/logout", headers=headers)
    assert logout_response.status_code == 204

    me_response = api_client.get("/wallet/v1/me", headers=headers)
    assert me_response.status_code == 401


def test_get_me_profile(api_client):
    body = _register_user(api_client, "profile@example.com")
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    response = api_client.get("/wallet/v1/me", headers=headers)
    assert response.status_code == 200

    profile = response.json()
    assert profile["email"] == "profile@example.com"
    assert profile["display_name"] == "Test User"
    assert profile["currency"] == "USD"
    assert profile["balance_microdollars"] == 0
    assert "wallet_id" in profile


def test_virtual_key_lifecycle(api_client, db_session):
    body = _register_user(api_client, "keys@example.com")
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    create_response = api_client.post(
        "/wallet/v1/keys",
        headers=headers,
        json={"name": "laptop", "rpm_limit": 30, "tpm_limit": 50_000},
    )
    assert create_response.status_code == 201

    created = create_response.json()
    assert created["name"] == "laptop"
    assert created["key"].startswith(KEY_PREFIX)
    assert created["key_prefix"] == created["key"][:12]
    assert resolve_virtual_key(db_session, created["key"]) is not None

    list_response = api_client.get("/wallet/v1/keys", headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()["data"]) == 1
    assert "key" not in list_response.json()["data"][0]

    rotate_response = api_client.post(
        f"/wallet/v1/keys/{created['id']}/rotate",
        headers=headers,
    )
    assert rotate_response.status_code == 201
    rotated = rotate_response.json()
    assert rotated["key"] != created["key"]
    assert resolve_virtual_key(db_session, created["key"]) is None
    assert resolve_virtual_key(db_session, rotated["key"]) is not None

    revoke_response = api_client.delete(
        f"/wallet/v1/keys/{rotated['id']}",
        headers=headers,
    )
    assert revoke_response.status_code == 204
    assert resolve_virtual_key(db_session, rotated["key"]) is None


def test_key_routes_require_auth(api_client):
    response = api_client.get("/wallet/v1/keys")
    assert response.status_code == 401


def test_existing_wallet_api_still_works(api_client, db_session, settings_env):
    user = create_user(db_session, "wallet-api@example.com", "secure-pass-99")
    get_or_create_wallet(db_session, user.id)
    token = issue_session(db_session, user).jwt_token
    headers = {"Authorization": f"Bearer {token}"}

    response = api_client.get("/wallet/v1/wallet", headers=headers)
    assert response.status_code == 200
    assert response.json()["balance_microdollars"] == 0
