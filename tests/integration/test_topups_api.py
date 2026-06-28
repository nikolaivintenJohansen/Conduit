import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import stripe
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.app.main import app
from services.shared.models import PaymentIntent, Wallet
from services.wallet.auth import create_user, issue_session
from services.wallet.deps import get_db
from services.wallet.payments import MIN_TOPUP_MICRODOLLARS


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
def stripe_env(settings_env, monkeypatch: pytest.MonkeyPatch):
    from services.shared.config import get_settings

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def auth_headers(db_session, settings_env) -> dict[str, str]:
    user = create_user(db_session, "topups@example.com", "secure-pass-99")
    wallet = Wallet(user_id=user.id, balance_microdollars=1_000_000)
    db_session.add(wallet)
    db_session.flush()
    token = issue_session(db_session, user).jwt_token
    return {"Authorization": f"Bearer {token}"}


def test_checkout_requires_auth(api_client, stripe_env):
    response = api_client.post(
        "/wallet/v1/topups/checkout",
        json={"amount_microdollars": MIN_TOPUP_MICRODOLLARS},
    )
    assert response.status_code == 401


def test_checkout_rejects_below_minimum(api_client, auth_headers, stripe_env):
    response = api_client.post(
        "/wallet/v1/topups/checkout",
        headers=auth_headers,
        json={"amount_microdollars": MIN_TOPUP_MICRODOLLARS - 1},
    )
    assert response.status_code == 422


def test_checkout_returns_stripe_url(api_client, auth_headers, stripe_env, db_session):
    mock_session = MagicMock()
    mock_session.id = "cs_test_checkout"
    mock_session.url = "https://checkout.stripe.com/test"

    with patch(
        "services.wallet.payments.stripe.checkout.Session.create",
        return_value=mock_session,
    ):
        response = api_client.post(
            "/wallet/v1/topups/checkout",
            headers={**auth_headers, "Idempotency-Key": str(uuid4())},
            json={"amount_microdollars": MIN_TOPUP_MICRODOLLARS},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["checkout_url"] == "https://checkout.stripe.com/test"
    assert "payment_intent_id" in body

    stored = db_session.scalar(
        select(PaymentIntent).where(PaymentIntent.stripe_checkout_session_id == "cs_test_checkout")
    )
    assert stored is not None
    assert stored.status == "pending"


def test_checkout_unconfigured_returns_503(api_client, auth_headers, settings_env):
    response = api_client.post(
        "/wallet/v1/topups/checkout",
        headers=auth_headers,
        json={"amount_microdollars": MIN_TOPUP_MICRODOLLARS},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["error"]["code"] == "payments_unavailable"


def test_webhook_requires_signature(api_client, stripe_env):
    response = api_client.post("/wallet/v1/webhooks/stripe", content=b"{}")
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "missing_signature"


def test_webhook_rejects_invalid_signature(api_client, stripe_env):
    with patch(
        "services.app.wallet.topups_routes.construct_stripe_event",
        side_effect=stripe.error.SignatureVerificationError("bad", "sig"),
    ):
        response = api_client.post(
            "/wallet/v1/webhooks/stripe",
            content=b"{}",
            headers={"Stripe-Signature": "bad"},
        )
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "invalid_signature"


def test_webhook_credits_wallet(api_client, db_session, sandbox_wallet, stripe_env):
    payment_intent = PaymentIntent(
        wallet_id=sandbox_wallet.id,
        amount_microdollars=1_500_000,
        status="pending",
        idempotency_key=f"checkout:{uuid4()}",
        stripe_checkout_session_id="cs_webhook_credit",
    )
    db_session.add(payment_intent)
    db_session.flush()

    event = {
        "id": "evt_webhook_credit",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_webhook_credit",
                "payment_status": "paid",
                "payment_intent": "pi_webhook_credit",
                "metadata": {
                    "wallet_id": str(sandbox_wallet.id),
                    "amount_microdollars": "1500000",
                },
            }
        },
    }
    payload = json.dumps(event).encode()

    with patch("services.app.wallet.topups_routes.construct_stripe_event", return_value=event):
        response = api_client.post(
            "/wallet/v1/webhooks/stripe",
            content=payload,
            headers={"Stripe-Signature": "test_sig"},
        )
    assert response.status_code == 200
    assert response.json()["received"] is True
    assert sandbox_wallet.balance_microdollars == 5_000_000 + 1_500_000


def test_webhook_is_idempotent(api_client, db_session, sandbox_wallet, stripe_env):
    payment_intent = PaymentIntent(
        wallet_id=sandbox_wallet.id,
        amount_microdollars=1_000_000,
        status="pending",
        idempotency_key=f"checkout:{uuid4()}",
        stripe_checkout_session_id="cs_webhook_idempotent",
    )
    db_session.add(payment_intent)
    db_session.flush()

    event = {
        "id": "evt_webhook_idempotent",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_webhook_idempotent",
                "payment_status": "paid",
                "payment_intent": "pi_webhook_idempotent",
                "metadata": {
                    "wallet_id": str(sandbox_wallet.id),
                    "amount_microdollars": "1000000",
                },
            }
        },
    }
    payload = json.dumps(event).encode()
    headers = {"Stripe-Signature": "test_sig"}

    with patch("services.app.wallet.topups_routes.construct_stripe_event", return_value=event):
        first = api_client.post("/wallet/v1/webhooks/stripe", content=payload, headers=headers)
        second = api_client.post("/wallet/v1/webhooks/stripe", content=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert sandbox_wallet.balance_microdollars == 5_000_000 + 1_000_000
