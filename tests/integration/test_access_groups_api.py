import pytest
from fastapi.testclient import TestClient

from services.app.main import app
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
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    reset_rate_limit_state()


@pytest.fixture
def auth_headers(api_client) -> dict[str, str]:
    response = api_client.post(
        "/wallet/v1/auth/register",
        json={
            "email": "access-groups@example.com",
            "password": "secure-pass-99",
            "display_name": "Access Groups User",
        },
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_access_group_crud(api_client, auth_headers, model_catalog):
    create_response = api_client.post(
        "/wallet/v1/access-groups",
        headers=auth_headers,
        json={
            "name": "mini-only",
            "description": "Only GPT-4o mini",
            "model_slugs": [model_catalog.slug],
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "mini-only"
    assert created["model_slugs"] == [model_catalog.slug]

    list_response = api_client.get("/wallet/v1/access-groups", headers=auth_headers)
    assert list_response.status_code == 200
    listed_ids = {item["id"] for item in list_response.json()["data"]}
    assert created["id"] in listed_ids

    get_response = api_client.get(
        f"/wallet/v1/access-groups/{created['id']}",
        headers=auth_headers,
    )
    assert get_response.status_code == 200
    assert get_response.json()["id"] == created["id"]

    patch_response = api_client.patch(
        f"/wallet/v1/access-groups/{created['id']}",
        headers=auth_headers,
        json={"name": "mini-only-v2"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "mini-only-v2"

    delete_response = api_client.delete(
        f"/wallet/v1/access-groups/{created['id']}",
        headers=auth_headers,
    )
    assert delete_response.status_code == 204

    missing_response = api_client.get(
        f"/wallet/v1/access-groups/{created['id']}",
        headers=auth_headers,
    )
    assert missing_response.status_code == 404


def test_create_access_group_invalid_model_slug(api_client, auth_headers):
    response = api_client.post(
        "/wallet/v1/access-groups",
        headers=auth_headers,
        json={"name": "bad", "model_slugs": ["does-not-exist"]},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "invalid_model_slug"


def test_list_model_catalog(api_client, auth_headers, model_catalog):
    response = api_client.get("/wallet/v1/models", headers=auth_headers)
    assert response.status_code == 200

    body = response.json()
    assert len(body["data"]) >= 1
    slugs = {item["slug"] for item in body["data"]}
    assert model_catalog.slug in slugs


def test_assign_access_group_to_key(
    api_client,
    auth_headers,
    db_session,
    model_catalog,
):
    group_response = api_client.post(
        "/wallet/v1/access-groups",
        headers=auth_headers,
        json={"name": "restricted", "model_slugs": [model_catalog.slug]},
    )
    group_id = group_response.json()["id"]

    key_response = api_client.post(
        "/wallet/v1/keys",
        headers=auth_headers,
        json={"name": "restricted-key"},
    )
    assert key_response.status_code == 201
    key_id = key_response.json()["id"]
    plaintext = key_response.json()["key"]
    assert key_response.json()["access_group_id"] is None

    patch_response = api_client.patch(
        f"/wallet/v1/keys/{key_id}",
        headers=auth_headers,
        json={"access_group_id": group_id},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["access_group_id"] == group_id

    from services.wallet.auth import get_user_by_email
    from services.wallet.ledger import get_wallet_by_user_id

    user = get_user_by_email(db_session, "access-groups@example.com")
    wallet = get_wallet_by_user_id(db_session, user.id)
    wallet.balance_microdollars = 5_000_000
    db_session.flush()

    denied = api_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {plaintext}"},
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["error"]["code"] == "model_not_allowed"


def test_create_key_with_access_group(api_client, auth_headers, model_catalog):
    group_response = api_client.post(
        "/wallet/v1/access-groups",
        headers=auth_headers,
        json={"name": "on-create", "model_slugs": [model_catalog.slug]},
    )
    group_id = group_response.json()["id"]

    key_response = api_client.post(
        "/wallet/v1/keys",
        headers=auth_headers,
        json={"name": "grouped-key", "access_group_id": group_id},
    )
    assert key_response.status_code == 201
    assert key_response.json()["access_group_id"] == group_id


def test_access_group_routes_require_auth(api_client):
    assert api_client.get("/wallet/v1/access-groups").status_code == 401
    assert api_client.get("/wallet/v1/models").status_code == 401
