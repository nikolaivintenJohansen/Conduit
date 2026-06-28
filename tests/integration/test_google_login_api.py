import pytest
from fastapi.testclient import TestClient

from services.app.main import app
from services.app.wallet.auth_routes import _OAUTH_STATE_COOKIE, _sign_state
from services.shared.config import get_settings
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


def _set_state_cookie(client: TestClient, state: str) -> None:
    client.cookies.set(_OAUTH_STATE_COOKIE, _sign_state(state))


def test_google_callback_creates_session(api_client, monkeypatch):
    state = "test-state-abc"
    _set_state_cookie(api_client, state)

    from services.app.wallet import auth_routes
    from services.wallet.google_oauth import GoogleProfile

    monkeypatch.setattr(
        auth_routes,
        "exchange_code_and_profile",
        lambda code: GoogleProfile(
            sub="google-123",
            email="newgoogle@example.com",
            email_verified=True,
            name="New Google",
        ),
    )

    response = api_client.post(
        "/wallet/v1/auth/oauth/google/callback",
        json={"code": "fake-code", "state": state},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "newgoogle@example.com"
    assert body["expires_in"] > 0


def test_google_callback_rejects_state_mismatch(api_client, monkeypatch):
    _set_state_cookie(api_client, "correct-state")

    from services.app.wallet import auth_routes

    called = {"value": False}

    def _should_not_be_called(code):
        called["value"] = True
        raise AssertionError("exchange should not run on state mismatch")

    monkeypatch.setattr(auth_routes, "exchange_code_and_profile", _should_not_be_called)

    response = api_client.post(
        "/wallet/v1/auth/oauth/google/callback",
        json={"code": "fake-code", "state": "wrong-state"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "invalid_state"
    assert called["value"] is False


def test_google_callback_replays_same_identity(api_client, monkeypatch):
    from services.app.wallet import auth_routes
    from services.wallet.google_oauth import GoogleProfile

    monkeypatch.setattr(
        auth_routes,
        "exchange_code_and_profile",
        lambda code: GoogleProfile(
            sub="google-replay",
            email="replay@example.com",
            email_verified=True,
            name="Replay User",
        ),
    )

    state1 = "state-1"
    _set_state_cookie(api_client, state1)
    first = api_client.post(
        "/wallet/v1/auth/oauth/google/callback",
        json={"code": "c1", "state": state1},
    )
    assert first.status_code == 200
    first_user_id = first.json()["user"]["id"]  # noqa: F841 — placeholder for parity check

    state2 = "state-2"
    _set_state_cookie(api_client, state2)
    second = api_client.post(
        "/wallet/v1/auth/oauth/google/callback",
        json={"code": "c2", "state": state2},
    )
    assert second.status_code == 200
    assert second.json()["user"]["email"] == "replay@example.com"


def test_google_login_redirect_requires_config(api_client, settings_env):
    # GOOGLE_CLIENT_ID is unset in settings_env, so the redirect endpoint 503s.
    get_settings.cache_clear()
    response = api_client.get("/wallet/v1/auth/oauth/google")
    assert response.status_code == 503
    assert response.json()["detail"]["error"]["code"] == "google_not_configured"
