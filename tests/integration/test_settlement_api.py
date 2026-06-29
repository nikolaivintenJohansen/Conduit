"""Integration tests for partner settlement + Connect onboarding endpoints (Phase 7)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from services.app.main import app
from services.gateway.rate_limit import reset_rate_limit_state
from services.shared.models import PartnerAccount, UsageEvent
from services.wallet.deps import get_db


class _FakeTransfer:
    def __init__(self, transfer_id: str) -> None:
        self.id = transfer_id


class _FakeTransfers:
    def __init__(self, transfer_id: str) -> None:
        self.transfer_id = transfer_id

    def create(self, **kwargs):  # noqa: ANN003
        return _FakeTransfer(self.transfer_id)


class _FakeStripe:
    def __init__(self, transfer_id: str = "tr_api_1") -> None:
        self.api_key = None
        self.Transfer = _FakeTransfers(transfer_id)


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
def stripe_configured(monkeypatch):
    from services.shared.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_settlement")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def fake_stripe(monkeypatch, stripe_configured):
    from services.wallet import settlement as settlement_service

    fake = _FakeStripe(transfer_id="tr_api_clear")
    monkeypatch.setattr(settlement_service, "stripe", fake)
    return fake


def _seed_usage(db_session, *, partner, user, wallet, count=3):
    from datetime import UTC, datetime, timedelta

    seeded_at = datetime.now(UTC) - timedelta(minutes=5)
    for i in range(count):
        db_session.add(
            UsageEvent(
                request_id=f"req-{partner.slug}-{i}-{uuid4().hex[:6]}",
                user_id=user.id,
                wallet_id=wallet.id,
                model="gpt-4o-mini",
                provider="openai",
                input_tokens=100,
                output_tokens=50,
                base_cost_microdollars=1_000_000,
                charged_microdollars=2_000_000,
                platform_fee_microdollars=200_000,
                partner_margin_microdollars=800_000,
                partner_account_id=partner.id,
                status="completed",
                created_at=seeded_at,
            )
        )
    db_session.flush()


def test_run_settlement_endpoint_clears_partner(
    api_client, db_session, sandbox_user, sandbox_wallet, fake_stripe, partner_admin_headers
):
    partner = PartnerAccount(
        name="Cursor",
        slug=f"cursor-{uuid4().hex[:6]}",
        stripe_connect_id="acct_cursor_1",
    )
    db_session.add(partner)
    db_session.flush()
    _seed_usage(
        db_session, partner=partner, user=sandbox_user, wallet=sandbox_wallet, count=3
    )

    response = api_client.post(
        f"/wallet/v1/partner/settlement/run?partner_slug={partner.slug}",
        headers=partner_admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cleared"] == 1
    assert body["failed"] == 0
    assert body["results"][0]["status"] == "cleared"
    assert body["results"][0]["event_count"] == 3


def test_run_settlement_requires_partner_admin_token(api_client, fake_stripe):
    response = api_client.post("/wallet/v1/partner/settlement/run")
    assert response.status_code == 401


def test_run_settlement_unknown_partner_404(
    api_client, fake_stripe, partner_admin_headers
):
    response = api_client.post(
        "/wallet/v1/partner/settlement/run?partner_slug=does-not-exist",
        headers=partner_admin_headers,
    )
    assert response.status_code == 404


def test_list_settlement_batches(api_client, db_session, sandbox_user, sandbox_wallet, fake_stripe, partner_admin_headers):
    partner = PartnerAccount(
        name="Lister",
        slug=f"lister-{uuid4().hex[:6]}",
        stripe_connect_id="acct_lister_1",
    )
    db_session.add(partner)
    db_session.flush()
    _seed_usage(
        db_session, partner=partner, user=sandbox_user, wallet=sandbox_wallet, count=2
    )

    run = api_client.post(
        f"/wallet/v1/partner/settlement/run?partner_slug={partner.slug}",
        headers=partner_admin_headers,
    )
    assert run.status_code == 200

    response = api_client.get(
        f"/wallet/v1/partner/{partner.slug}/settlement/batches",
        headers=partner_admin_headers,
    )
    assert response.status_code == 200
    batches = response.json()["data"]
    assert len(batches) == 1
    assert batches[0]["status"] == "cleared"
    assert batches[0]["stripe_transfer_id"] == "tr_api_clear"
    assert batches[0]["event_count"] == 2


def test_connect_status_without_stripe_configured(api_client, db_session, partner_admin_headers):
    partner = PartnerAccount(name="NoStripe", slug=f"nostripe-{uuid4().hex[:6]}")
    db_session.add(partner)
    db_session.flush()
    response = api_client.get(
        f"/wallet/v1/partner/{partner.slug}/connect/status",
        headers=partner_admin_headers,
    )
    assert response.status_code == 503


def test_account_updated_webhook_refreshes_capabilities(
    api_client, db_session, settings_env, monkeypatch, partner_admin_headers
):
    from services.shared.config import get_settings
    from services.app.wallet import topups_routes

    get_settings.cache_clear()
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_webhook")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    get_settings.cache_clear()

    partner = PartnerAccount(
        name="WebhookPartner",
        slug=f"wh-{uuid4().hex[:6]}",
        stripe_connect_id="acct_wh_1",
    )
    db_session.add(partner)
    db_session.flush()

    # Bypass signature verification for the test.
    monkeypatch.setattr(
        topups_routes,
        "construct_stripe_event",
        lambda payload, sig: {
            "id": "evt_acct_1",
            "type": "account.updated",
            "data": {
                "object": SimpleNamespace(
                    id="acct_wh_1",
                    charges_enabled=True,
                    details_submitted=True,
                    payouts_enabled=True,
                    capabilities={"transfers": "active"},
                )
            },
        },
    )

    response = api_client.post(
        "/wallet/v1/webhooks/stripe",
        data=b"{}",
        headers={"Stripe-Signature": "t=1,v1=x", **partner_admin_headers},
    )
    assert response.status_code == 200

    refreshed = db_session.get(PartnerAccount, partner.id)
    assert refreshed.stripe_capabilities_json["payouts_enabled"] is True
    assert refreshed.stripe_capabilities_json["charges_enabled"] is True
