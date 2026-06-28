import pytest
from fastapi.testclient import TestClient

from services.app.main import app
from services.gateway.rate_limit import reset_rate_limit_state
from services.shared.models import UsageEvent, VirtualKey, Wallet
from services.wallet.keys import generate_virtual_key


@pytest.fixture
def api_client(db_session, settings_env):
    from services.wallet.deps import get_db

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    reset_rate_limit_state()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    reset_rate_limit_state()


@pytest.fixture
def gateway_headers(db_session, sandbox_user, model_catalog) -> dict[str, str]:
    generated = generate_virtual_key()
    vkey = VirtualKey(
        user_id=sandbox_user.id,
        name="gateway-test-key",
        key_prefix=generated.prefix,
        key_hash=generated.key_hash,
        rpm_limit=60,
        tpm_limit=100_000,
    )
    db_session.add(vkey)
    wallet = Wallet(user_id=sandbox_user.id, balance_microdollars=5_000_000)
    db_session.add(wallet)
    db_session.flush()
    return {"Authorization": f"Bearer {generated.plaintext}"}


def test_chat_completion_success(api_client, gateway_headers, db_session, sandbox_user):
    response = api_client.post(
        "/v1/chat/completions",
        headers=gateway_headers,
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello gateway"}],
        },
    )
    assert response.status_code == 200

    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "gpt-4o-mini"
    assert body["choices"][0]["message"]["content"]
    assert body["usage"]["total_tokens"] > 0
    assert "X-Request-Id" in response.headers
    assert "X-UAW-Cost-USD" in response.headers
    assert "X-UAW-Balance-Remaining-USD" in response.headers

    wallet = db_session.query(Wallet).filter_by(user_id=sandbox_user.id).one()
    assert wallet.balance_microdollars < 5_000_000

    usage_events = db_session.query(UsageEvent).filter_by(user_id=sandbox_user.id).all()
    assert len(usage_events) == 1
    assert usage_events[0].model == "gpt-4o-mini"
    assert usage_events[0].charged_microdollars > 0


def test_chat_completion_invalid_api_key(api_client):
    response = api_client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer sk-uaw-invalid"},
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "invalid_api_key"


def test_chat_completion_insufficient_balance(api_client, db_session, sandbox_user, model_catalog):
    generated = generate_virtual_key()
    vkey = VirtualKey(
        user_id=sandbox_user.id,
        key_prefix=generated.prefix,
        key_hash=generated.key_hash,
    )
    db_session.add(vkey)
    wallet = Wallet(user_id=sandbox_user.id, balance_microdollars=0)
    db_session.add(wallet)
    db_session.flush()

    response = api_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {generated.plaintext}"},
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 402
    assert response.json()["detail"]["error"]["code"] == "insufficient_balance"


def test_chat_completion_model_not_allowed(
    api_client, db_session, sandbox_user, restricted_access_group
):
    generated = generate_virtual_key()
    vkey = VirtualKey(
        user_id=sandbox_user.id,
        access_group_id=restricted_access_group.id,
        key_prefix=generated.prefix,
        key_hash=generated.key_hash,
    )
    db_session.add(vkey)
    wallet = Wallet(user_id=sandbox_user.id, balance_microdollars=5_000_000)
    db_session.add(wallet)
    db_session.flush()

    response = api_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {generated.plaintext}"},
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["error"]["code"] == "model_not_allowed"


def test_list_models_filtered_by_access_group(
    api_client, db_session, sandbox_user, restricted_access_group, model_catalog
):
    generated = generate_virtual_key()
    vkey = VirtualKey(
        user_id=sandbox_user.id,
        access_group_id=restricted_access_group.id,
        key_prefix=generated.prefix,
        key_hash=generated.key_hash,
    )
    db_session.add(vkey)
    db_session.flush()

    response = api_client.get(
        "/v1/models",
        headers={"Authorization": f"Bearer {generated.plaintext}"},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["object"] == "list"
    assert len(body["data"]) == 1
    assert body["data"][0]["id"] == model_catalog.slug


def test_rate_limit_exceeded(api_client, db_session, sandbox_user, model_catalog):
    generated = generate_virtual_key()
    vkey = VirtualKey(
        user_id=sandbox_user.id,
        key_prefix=generated.prefix,
        key_hash=generated.key_hash,
        rpm_limit=1,
        tpm_limit=100_000,
    )
    db_session.add(vkey)
    wallet = Wallet(user_id=sandbox_user.id, balance_microdollars=5_000_000)
    db_session.add(wallet)
    db_session.flush()
    headers = {"Authorization": f"Bearer {generated.plaintext}"}
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "hello"}],
    }

    first = api_client.post("/v1/chat/completions", headers=headers, json=payload)
    second = api_client.post("/v1/chat/completions", headers=headers, json=payload)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"]["error"]["code"] == "rate_limit_exceeded"
