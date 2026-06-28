from uuid import UUID, uuid4

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from services.shared.config import get_settings
from services.shared.models import Wallet
from services.wallet.deps import get_current_wallet, get_db
from services.wallet.payments import (
    MIN_TOPUP_MICRODOLLARS,
    construct_stripe_event,
    create_topup_checkout,
    handle_stripe_webhook_event,
)

router = APIRouter(prefix="/wallet/v1", tags=["Topups"])


class CheckoutRequest(BaseModel):
    amount_microdollars: int = Field(ge=MIN_TOPUP_MICRODOLLARS)


class CheckoutResponse(BaseModel):
    checkout_url: str
    payment_intent_id: UUID


class WebhookResponse(BaseModel):
    received: bool = True


@router.post("/topups/checkout", response_model=CheckoutResponse)
def create_checkout(
    body: CheckoutRequest,
    wallet: Wallet = Depends(get_current_wallet),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CheckoutResponse:
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "payments_unavailable",
                    "message": "Stripe payments are not configured",
                }
            },
        )

    try:
        result = create_topup_checkout(
            db,
            wallet_id=wallet.id,
            amount_microdollars=body.amount_microdollars,
            idempotency_key=idempotency_key or str(uuid4()),
            success_url=settings.stripe_checkout_success_url,
            cancel_url=settings.stripe_checkout_cancel_url,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_topup", "message": str(exc)}},
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "payments_unavailable", "message": str(exc)}},
        ) from exc

    return CheckoutResponse(
        checkout_url=result.checkout_url,
        payment_intent_id=result.payment_intent.id,
    )


@router.post("/webhooks/stripe", response_model=WebhookResponse)
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> WebhookResponse:
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "payments_unavailable",
                    "message": "Stripe webhooks are not configured",
                }
            },
        )

    payload = await request.body()
    signature = request.headers.get("Stripe-Signature")
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "missing_signature",
                    "message": "Stripe-Signature header is required",
                }
            },
        )

    try:
        event = construct_stripe_event(payload, signature)
    except stripe.error.SignatureVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_signature", "message": "Invalid webhook signature"}},
        ) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_webhook", "message": str(exc)}},
        ) from exc

    handle_stripe_webhook_event(db, event)
    return WebhookResponse()
