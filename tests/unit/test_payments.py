from uuid import uuid4

from sqlalchemy import select

from services.shared.models import PaymentIntent
from services.wallet.payments import (
    MIN_TOPUP_MICRODOLLARS,
    handle_stripe_webhook_event,
    mark_payment_failed,
    process_stripe_topup_webhook,
)


def test_mark_payment_failed_updates_pending_intent(db_session, sandbox_wallet):
    payment_intent = PaymentIntent(
        wallet_id=sandbox_wallet.id,
        amount_microdollars=1_000_000,
        status="pending",
        idempotency_key=f"checkout:{uuid4()}",
        stripe_checkout_session_id="cs_failed_1",
    )
    db_session.add(payment_intent)
    db_session.flush()

    updated = mark_payment_failed(db_session, stripe_checkout_session_id="cs_failed_1")
    assert updated is not None
    assert updated.status == "failed"


def test_mark_payment_failed_does_not_override_succeeded(db_session, sandbox_wallet):
    process_stripe_topup_webhook(
        db_session,
        wallet_id=sandbox_wallet.id,
        amount_microdollars=1_000_000,
        stripe_event_id="evt_succeeded_1",
        stripe_checkout_session_id="cs_succeeded_1",
    )

    updated = mark_payment_failed(db_session, stripe_checkout_session_id="cs_succeeded_1")
    assert updated is not None
    assert updated.status == "succeeded"


def test_handle_checkout_completed_event(db_session, sandbox_wallet):
    payment_intent = PaymentIntent(
        wallet_id=sandbox_wallet.id,
        amount_microdollars=2_000_000,
        status="pending",
        idempotency_key=f"checkout:{uuid4()}",
        stripe_checkout_session_id="cs_completed_1",
    )
    db_session.add(payment_intent)
    db_session.flush()

    event = {
        "id": "evt_completed_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_completed_1",
                "payment_status": "paid",
                "payment_intent": "pi_completed_1",
                "metadata": {
                    "wallet_id": str(sandbox_wallet.id),
                    "amount_microdollars": "2000000",
                },
            }
        },
    }

    result = handle_stripe_webhook_event(db_session, event)
    assert result is not None
    assert result.created
    assert sandbox_wallet.balance_microdollars == 5_000_000 + 2_000_000

    stored = db_session.scalar(
        select(PaymentIntent).where(PaymentIntent.stripe_checkout_session_id == "cs_completed_1")
    )
    assert stored is not None
    assert stored.status == "succeeded"
    assert stored.stripe_payment_intent_id == "pi_completed_1"


def test_handle_checkout_completed_event_with_real_stripe_object(db_session, sandbox_wallet):
    """Regression: stripe>=12 StripeObject is not a dict subclass, so the handler
    must normalize via to_dict() before calling .get() on the data object."""
    import stripe

    obj = stripe.StripeObject.construct_from(
        {
            "id": "cs_stripeobj_1",
            "payment_status": "paid",
            "payment_intent": "pi_stripeobj_1",
            "metadata": {
                "wallet_id": str(sandbox_wallet.id),
                "amount_microdollars": "1500000",
            },
        },
        "sk_test_x",
    )
    event = {
        "id": "evt_stripeobj_1",
        "type": "checkout.session.completed",
        "data": {"object": obj},
    }

    result = handle_stripe_webhook_event(db_session, event)
    assert result is not None
    assert result.created
    assert sandbox_wallet.balance_microdollars == 5_000_000 + 1_500_000


def test_handle_checkout_completed_ignores_unpaid(db_session, sandbox_wallet):
    event = {
        "id": "evt_unpaid_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_unpaid_1",
                "payment_status": "unpaid",
                "metadata": {
                    "wallet_id": str(sandbox_wallet.id),
                    "amount_microdollars": "1000000",
                },
            }
        },
    }

    result = handle_stripe_webhook_event(db_session, event)
    assert result is None
    assert sandbox_wallet.balance_microdollars == 5_000_000


def test_handle_async_payment_failed_marks_intent(db_session, sandbox_wallet):
    payment_intent = PaymentIntent(
        wallet_id=sandbox_wallet.id,
        amount_microdollars=MIN_TOPUP_MICRODOLLARS,
        status="pending",
        idempotency_key=f"checkout:{uuid4()}",
        stripe_checkout_session_id="cs_async_failed",
    )
    db_session.add(payment_intent)
    db_session.flush()

    event = {
        "id": "evt_async_failed",
        "type": "checkout.session.async_payment_failed",
        "data": {"object": {"id": "cs_async_failed"}},
    }

    assert handle_stripe_webhook_event(db_session, event) is None
    assert payment_intent.status == "failed"
