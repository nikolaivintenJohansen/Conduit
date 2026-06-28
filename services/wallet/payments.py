from dataclasses import dataclass
from uuid import UUID

import stripe
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.shared.config import get_settings
from services.shared.models import LedgerEntry, PaymentIntent
from services.wallet.ledger import LedgerResult, credit_wallet

MIN_TOPUP_MICRODOLLARS = 500_000
CHECKOUT_IDEMPOTENCY_PREFIX = "checkout:"


@dataclass(frozen=True)
class CheckoutResult:
    payment_intent: PaymentIntent
    checkout_url: str


@dataclass(frozen=True)
class WebhookCreditResult:
    payment_intent: PaymentIntent
    ledger: LedgerResult | None
    created: bool


def _configure_stripe() -> None:
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise RuntimeError("Stripe is not configured")
    stripe.api_key = settings.stripe_secret_key


def _microdollars_to_stripe_cents(amount_microdollars: int) -> int:
    return amount_microdollars // 10_000


def _find_payment_intent(
    session: Session,
    *,
    stripe_checkout_session_id: str | None = None,
    stripe_payment_intent_id: str | None = None,
    idempotency_key: str | None = None,
) -> PaymentIntent | None:
    if stripe_checkout_session_id:
        found = session.scalar(
            select(PaymentIntent).where(
                PaymentIntent.stripe_checkout_session_id == stripe_checkout_session_id
            )
        )
        if found is not None:
            return found

    if stripe_payment_intent_id:
        found = session.scalar(
            select(PaymentIntent).where(
                PaymentIntent.stripe_payment_intent_id == stripe_payment_intent_id
            )
        )
        if found is not None:
            return found

    if idempotency_key:
        return session.scalar(
            select(PaymentIntent).where(PaymentIntent.idempotency_key == idempotency_key)
        )
    return None


def create_topup_checkout(
    session: Session,
    *,
    wallet_id: UUID,
    amount_microdollars: int,
    idempotency_key: str,
    success_url: str,
    cancel_url: str,
) -> CheckoutResult:
    if amount_microdollars < MIN_TOPUP_MICRODOLLARS:
        raise ValueError(f"minimum top-up is {MIN_TOPUP_MICRODOLLARS} microdollars")

    checkout_key = f"{CHECKOUT_IDEMPOTENCY_PREFIX}{idempotency_key}"
    existing = _find_payment_intent(session, idempotency_key=checkout_key)
    if existing is not None:
        if existing.status == "succeeded":
            raise ValueError("top-up already completed")
        if existing.stripe_checkout_session_id:
            _configure_stripe()
            stripe_session = stripe.checkout.Session.retrieve(existing.stripe_checkout_session_id)
            if stripe_session.url:
                return CheckoutResult(
                    payment_intent=existing,
                    checkout_url=stripe_session.url,
                )
        raise ValueError("pending checkout is unavailable")

    payment_intent = PaymentIntent(
        wallet_id=wallet_id,
        amount_microdollars=amount_microdollars,
        status="pending",
        idempotency_key=checkout_key,
    )
    session.add(payment_intent)
    session.flush()

    _configure_stripe()
    stripe_session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "AI Wallet Top-up"},
                    "unit_amount": _microdollars_to_stripe_cents(amount_microdollars),
                },
                "quantity": 1,
            }
        ],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "wallet_id": str(wallet_id),
            "payment_intent_id": str(payment_intent.id),
            "amount_microdollars": str(amount_microdollars),
        },
        client_reference_id=str(payment_intent.id),
    )

    payment_intent.stripe_checkout_session_id = stripe_session.id
    session.flush()
    if not stripe_session.url:
        raise RuntimeError("Stripe checkout session missing URL")

    return CheckoutResult(payment_intent=payment_intent, checkout_url=stripe_session.url)


def mark_payment_failed(
    session: Session,
    *,
    stripe_checkout_session_id: str | None = None,
    stripe_payment_intent_id: str | None = None,
) -> PaymentIntent | None:
    payment_intent = _find_payment_intent(
        session,
        stripe_checkout_session_id=stripe_checkout_session_id,
        stripe_payment_intent_id=stripe_payment_intent_id,
    )
    if payment_intent is None or payment_intent.status == "succeeded":
        return payment_intent

    payment_intent.status = "failed"
    session.flush()
    return payment_intent


def process_stripe_topup_webhook(
    session: Session,
    *,
    wallet_id: UUID,
    amount_microdollars: int,
    stripe_event_id: str,
    stripe_checkout_session_id: str | None = None,
    stripe_payment_intent_id: str | None = None,
) -> WebhookCreditResult:
    """Idempotent Stripe webhook handler — credits wallet once per event."""
    existing_ledger = session.scalar(
        select(LedgerEntry).where(
            LedgerEntry.wallet_id == wallet_id,
            LedgerEntry.idempotency_key == f"stripe:{stripe_event_id}",
        )
    )
    if existing_ledger is not None:
        payment_intent = _find_payment_intent(
            session,
            stripe_checkout_session_id=stripe_checkout_session_id,
            stripe_payment_intent_id=stripe_payment_intent_id,
            idempotency_key=stripe_event_id,
        )
        if payment_intent is None:
            payment_intent = session.scalar(
                select(PaymentIntent).where(PaymentIntent.ledger_entry_id == existing_ledger.id)
            )
        assert payment_intent is not None
        return WebhookCreditResult(payment_intent=payment_intent, ledger=None, created=False)

    payment_intent = _find_payment_intent(
        session,
        stripe_checkout_session_id=stripe_checkout_session_id,
        stripe_payment_intent_id=stripe_payment_intent_id,
        idempotency_key=stripe_event_id,
    )
    if payment_intent is not None and payment_intent.status == "succeeded":
        return WebhookCreditResult(payment_intent=payment_intent, ledger=None, created=False)

    if payment_intent is None:
        payment_intent = PaymentIntent(
            wallet_id=wallet_id,
            amount_microdollars=amount_microdollars,
            status="pending",
            idempotency_key=stripe_event_id,
            stripe_checkout_session_id=stripe_checkout_session_id,
            stripe_payment_intent_id=stripe_payment_intent_id,
        )
        session.add(payment_intent)
        session.flush()
    else:
        if stripe_payment_intent_id and not payment_intent.stripe_payment_intent_id:
            payment_intent.stripe_payment_intent_id = stripe_payment_intent_id

    ledger = credit_wallet(
        session,
        wallet_id,
        amount_microdollars,
        idempotency_key=f"stripe:{stripe_event_id}",
        reference_type="payment_intent",
        reference_id=payment_intent.id,
        metadata={
            "stripe_event_id": stripe_event_id,
            "stripe_checkout_session_id": stripe_checkout_session_id,
            "stripe_payment_intent_id": stripe_payment_intent_id,
        },
    )
    payment_intent.status = "succeeded"
    payment_intent.ledger_entry_id = ledger.entry.id
    session.flush()
    return WebhookCreditResult(
        payment_intent=payment_intent,
        ledger=ledger,
        created=ledger.created,
    )


def construct_stripe_event(payload: bytes, signature_header: str) -> stripe.Event:
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise RuntimeError("Stripe webhook secret is not configured")
    return stripe.Webhook.construct_event(
        payload,
        signature_header,
        settings.stripe_webhook_secret,
    )


def handle_stripe_webhook_event(
    session: Session, event: stripe.Event
) -> WebhookCreditResult | None:
    event_type = event["type"]
    event_id = event["id"]
    data_object = event["data"]["object"]

    if event_type == "checkout.session.completed":
        if data_object.get("payment_status") != "paid":
            return None

        metadata = data_object.get("metadata") or {}
        wallet_id = UUID(metadata["wallet_id"])
        amount_microdollars = int(metadata["amount_microdollars"])
        return process_stripe_topup_webhook(
            session,
            wallet_id=wallet_id,
            amount_microdollars=amount_microdollars,
            stripe_event_id=event_id,
            stripe_checkout_session_id=data_object["id"],
            stripe_payment_intent_id=data_object.get("payment_intent"),
        )

    if event_type in {"checkout.session.async_payment_failed", "checkout.session.expired"}:
        mark_payment_failed(session, stripe_checkout_session_id=data_object["id"])
        return None

    if event_type == "payment_intent.payment_failed":
        mark_payment_failed(session, stripe_payment_intent_id=data_object["id"])
        return None

    return None
