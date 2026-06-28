import pytest
from fastapi.testclient import TestClient

from services.app.main import app
from services.gateway.allowance_cache import reset_allowance_cache
from services.gateway.rate_limit import reset_rate_limit_state
from services.shared.models import UsageEvent, Wallet
from services.wallet.apps import connect_app, revoke_app
from services.wallet.deps import get_db
from services.wallet.oauth import create_authorization_code, exchange_code_for_tokens


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
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    reset_rate_limit_state()
    reset_allowance_cache()


def _make_app_token(db_session, user, app_registration, install) -> str:
    code = create_authorization_code(
        db_session,
        client_id=app_registration.client_id,
        user_id=user.id,
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
    return tokens.access_token


def test_app_access_token_is_honored_and_increments_allowance(
    api_client, db_session, sandbox_user, sandbox_wallet, app_registration, connected_app
):
    token = _make_app_token(db_session, sandbox_user, app_registration, connected_app)

    response = api_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello from partner app"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["object"] == "chat.completion"

    # Wallet debited.
    wallet = db_session.query(Wallet).filter_by(user_id=sandbox_user.id).one()
    assert wallet.balance_microdollars < 5_000_000

    # Usage recorded and app-scoped.
    events = db_session.query(UsageEvent).filter_by(user_id=sandbox_user.id).all()
    assert len(events) == 1
    assert events[0].metadata_json.get("app_install_id") == str(connected_app.id)

    # Per-app allowance incremented (authoritative DB row).
    db_session.refresh(connected_app)
    assert connected_app.allowance_spent_microdollars > 0


def test_allowance_exceeded_returns_402(
    api_client, db_session, sandbox_user, sandbox_wallet, app_registration
):
    install = connect_app(
        db_session,
        user_id=sandbox_user.id,
        client_id=app_registration.client_id,
        spend_limit_microdollars=50_000,  # $0.05 — below the pessimistic hold estimate
    )
    token = _make_app_token(db_session, sandbox_user, app_registration, install)

    response = api_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "should be blocked"}],
        },
    )
    assert response.status_code == 402
    assert response.json()["detail"]["error"]["code"] == "allowance_exceeded"

    # No usage recorded, no debit.
    events = db_session.query(UsageEvent).filter_by(user_id=sandbox_user.id).all()
    assert events == []


def test_revoked_install_returns_401(
    api_client, db_session, sandbox_user, sandbox_wallet, app_registration, connected_app
):
    token = _make_app_token(db_session, sandbox_user, app_registration, connected_app)
    revoke_app(db_session, user_id=sandbox_user.id, install_id=connected_app.id)
    db_session.flush()

    response = api_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "should be blocked"}],
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "app_revoked"


def test_virtual_key_path_still_works_after_refactor(
    api_client, db_session, sandbox_user, sandbox_wallet, model_catalog
):
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
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {generated.plaintext}"},
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 200
