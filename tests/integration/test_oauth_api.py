import base64
import hashlib
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from services.app.main import app
from services.shared.models import PartnerAccount
from services.wallet.app_registrations import create_app_registration
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
    user = create_user(db_session, f"oauth-{uuid4()}@example.com", "super-password-1")
    partner = PartnerAccount(name="P", slug=f"p-{uuid4().hex[:8]}")
    db_session.add(partner)
    db_session.flush()
    created = create_app_registration(
        db_session,
        partner_account_id=partner.id,
        name="FlowApp",
        redirect_uris=["https://flow.example.com/cb"],
    )
    token = issue_session(db_session, user).jwt_token
    return user, created, token


def _pkce_pair():
    verifier = "v" * 43
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    return verifier, challenge


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_oidc_discovery_and_jwks(api_client):
    discovery = api_client.get("/.well-known/openid-configuration")
    assert discovery.status_code == 200
    body = discovery.json()
    assert body["issuer"].endswith("localhost:8000") or "localhost" in body["issuer"]
    assert body["authorization_endpoint"].endswith("/oauth/authorize")

    jwks = api_client.get("/oauth/jwks")
    assert jwks.status_code == 200
    assert jwks.json() == {"keys": []}


def test_full_authorize_consent_token_userinfo_flow(api_client, user_and_app):
    user, created, token = user_and_app
    verifier, challenge = _pkce_pair()

    # 1. Authorize descriptor
    params = {
        "client_id": created.record.client_id,
        "redirect_uri": "https://flow.example.com/cb",
        "response_type": "code",
        "state": "xyz",
        "scope": "wallet:charge profile:read",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    desc = api_client.get("/oauth/authorize", params=params, headers=_headers(token))
    assert desc.status_code == 200
    assert desc.json()["app_name"] == "FlowApp"
    assert "wallet:charge" in desc.json()["requested_scopes"]

    # 2. Consent -> issue code
    consent = api_client.post(
        "/oauth/authorize/consent",
        headers=_headers(token),
        json={
            **params,
            "spend_limit_microdollars": 5_000_000,
            "reset_period": "monthly",
        },
    )
    assert consent.status_code == 200
    code = consent.json()["code"]
    assert "code=" in consent.json()["redirect_uri"]
    assert "state=xyz" in consent.json()["redirect_uri"]

    # 3. Token exchange (form-encoded)
    token_res = api_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": "https://flow.example.com/cb",
            "client_id": created.record.client_id,
            "client_secret": created.client_secret,
        },
    )
    assert token_res.status_code == 200
    tokens = token_res.json()
    assert tokens["access_token"]
    assert tokens["id_token"]
    assert tokens["refresh_token"]
    assert tokens["token_type"] == "Bearer"

    # 4. Userinfo
    userinfo = api_client.get(
        "/oauth/userinfo",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert userinfo.status_code == 200
    info = userinfo.json()
    assert info["sub"] == str(user.id)
    assert info["email"] == user.email


def test_authorize_rejects_unregistered_redirect(api_client, user_and_app):
    _, created, token = user_and_app
    res = api_client.get(
        "/oauth/authorize",
        params={
            "client_id": created.record.client_id,
            "redirect_uri": "https://evil.example.com/cb",
        },
        headers=_headers(token),
    )
    assert res.status_code == 400
    assert res.json()["detail"]["error"]["code"] == "invalid_redirect_uri"


def test_authorize_requires_session(api_client, user_and_app):
    _, created, _ = user_and_app
    res = api_client.get(
        "/oauth/authorize",
        params={
            "client_id": created.record.client_id,
            "redirect_uri": "https://flow.example.com/cb",
        },
    )
    assert res.status_code == 401


def test_token_rejects_pkce_mismatch(api_client, user_and_app):
    user, created, token = user_and_app
    _, challenge = _pkce_pair()
    consent = api_client.post(
        "/oauth/authorize/consent",
        headers=_headers(token),
        json={
            "client_id": created.record.client_id,
            "redirect_uri": "https://flow.example.com/cb",
            "code_challenge": challenge,
            "spend_limit_microdollars": 1_000_000,
        },
    )
    code = consent.json()["code"]

    res = api_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": "wrong-verifier",
            "redirect_uri": "https://flow.example.com/cb",
            "client_id": created.record.client_id,
            "client_secret": created.client_secret,
        },
    )
    assert res.status_code == 400
    assert res.json()["detail"]["error"] == "invalid_grant"


def test_refresh_token_flow(api_client, user_and_app):
    _, created, token = user_and_app
    consent = api_client.post(
        "/oauth/authorize/consent",
        headers=_headers(token),
        json={
            "client_id": created.record.client_id,
            "redirect_uri": "https://flow.example.com/cb",
            "spend_limit_microdollars": 1_000_000,
        },
    )
    code = consent.json()["code"]
    tokens = api_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://flow.example.com/cb",
            "client_id": created.record.client_id,
            "client_secret": created.client_secret,
        },
    ).json()

    refreshed = api_client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": created.record.client_id,
            "client_secret": created.client_secret,
        },
    )
    assert refreshed.status_code == 200
    body = refreshed.json()
    assert body["access_token"]
    assert body["refresh_token"] != tokens["refresh_token"]

    # Old refresh token is revoked.
    replay = api_client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": created.record.client_id,
            "client_secret": created.client_secret,
        },
    )
    assert replay.status_code == 400
    assert replay.json()["detail"]["error"] == "invalid_grant"


def test_consent_page_serves(api_client):
    res = api_client.get("/oauth/consent")
    assert res.status_code == 200
    assert "AI Wallet" in res.text
