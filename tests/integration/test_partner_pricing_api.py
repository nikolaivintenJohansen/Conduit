import pytest
from fastapi.testclient import TestClient

from services.app.main import app
from services.gateway.rate_limit import reset_rate_limit_state
from services.shared.models import UsageEvent, VirtualKey, Wallet
from services.wallet.deps import get_db
from services.wallet.keys import generate_virtual_key


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


def test_get_partner_account(api_client, partner_with_pricing, partner_admin_headers):
    response = api_client.get(
        f"/wallet/v1/partner/{partner_with_pricing.slug}",
        headers=partner_admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == partner_with_pricing.slug
    assert body["default_platform_fee_bps"] == 500


def test_create_price_rule(api_client, partner_with_pricing, model_catalog, partner_admin_headers):
    response = api_client.post(
        f"/wallet/v1/partner/{partner_with_pricing.slug}/price-rules",
        headers=partner_admin_headers,
        json={
            "model_slug": model_catalog.slug,
            "markup_bps": 2500,
            "price_per_m_input_microdollars": 300_000,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["model_slug"] == model_catalog.slug
    assert body["markup_bps"] == 2500
    assert body["price_per_m_input_microdollars"] == 300_000


def test_partner_admin_requires_token(api_client, partner_with_pricing):
    response = api_client.get(f"/wallet/v1/partner/{partner_with_pricing.slug}")
    assert response.status_code == 401


def test_gateway_applies_partner_pricing(
    api_client,
    db_session,
    sandbox_user,
    model_catalog,
    partner_with_pricing,
):
    generated = generate_virtual_key()
    vkey = VirtualKey(
        user_id=sandbox_user.id,
        partner_account_id=partner_with_pricing.id,
        key_prefix=generated.prefix,
        key_hash=generated.key_hash,
    )
    db_session.add(vkey)
    wallet = Wallet(user_id=sandbox_user.id, balance_microdollars=50_000_000)
    db_session.add(wallet)
    db_session.flush()

    response = api_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {generated.plaintext}"},
        json={
            "model": model_catalog.slug,
            "messages": [{"role": "user", "content": "partner pricing test"}],
        },
    )
    assert response.status_code == 200

    usage = db_session.query(UsageEvent).filter_by(user_id=sandbox_user.id).one()
    assert usage.partner_account_id == partner_with_pricing.id
    assert usage.charged_microdollars >= usage.base_cost_microdollars
    assert usage.platform_fee_microdollars >= 0
    assert usage.partner_margin_microdollars >= 0
    assert (
        usage.charged_microdollars
        == usage.base_cost_microdollars
        + usage.partner_margin_microdollars
        + usage.platform_fee_microdollars
    )
    assert usage.charged_microdollars > usage.base_cost_microdollars
