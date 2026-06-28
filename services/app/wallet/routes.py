from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from services.shared.models import User, Wallet
from services.wallet.balance import (
    get_wallet_summary_for_user,
    list_transactions,
    update_wallet_settings,
)
from services.wallet.deps import get_current_user, get_current_wallet, get_db

router = APIRouter(prefix="/wallet/v1", tags=["Wallet"])


class WalletResponse(BaseModel):
    wallet_id: UUID
    balance_microdollars: int
    held_microdollars: int
    available_microdollars: int
    currency: str
    low_balance_threshold_microdollars: int
    spend_limit_microdollars: int | None = None
    monthly_spend_microdollars: int = 0


class WalletSettingsRequest(BaseModel):
    spend_limit_microdollars: int | None = None
    low_balance_threshold_microdollars: int | None = Field(default=None, ge=0)


def _wallet_response(summary) -> WalletResponse:
    return WalletResponse(
        wallet_id=summary.wallet_id,
        balance_microdollars=summary.balance_microdollars,
        held_microdollars=summary.held_microdollars,
        available_microdollars=summary.available_microdollars,
        currency=summary.currency,
        low_balance_threshold_microdollars=summary.low_balance_threshold_microdollars,
        spend_limit_microdollars=summary.spend_limit_microdollars,
        monthly_spend_microdollars=summary.monthly_spend_microdollars,
    )


class LedgerEntryResponse(BaseModel):
    id: UUID
    entry_type: str
    amount_microdollars: int
    balance_after_microdollars: int
    created_at: datetime


class TransactionListResponse(BaseModel):
    data: list[LedgerEntryResponse]
    next_cursor: str | None = None


@router.get("/wallet", response_model=WalletResponse)
def get_wallet_balance(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WalletResponse:
    summary = get_wallet_summary_for_user(db, user.id)
    return _wallet_response(summary)


@router.patch("/wallet/settings", response_model=WalletResponse)
def patch_wallet_settings(
    body: WalletSettingsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WalletResponse:
    fields_set = body.model_fields_set
    try:
        summary = update_wallet_settings(
            db,
            user.id,
            spend_limit_microdollars=body.spend_limit_microdollars
            if "spend_limit_microdollars" in fields_set
            else ...,
            low_balance_threshold_microdollars=body.low_balance_threshold_microdollars
            if "low_balance_threshold_microdollars" in fields_set
            else ...,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_settings", "message": str(exc)}},
        ) from exc
    return _wallet_response(summary)


@router.get("/wallet/transactions", response_model=TransactionListResponse)
def get_wallet_transactions(
    wallet: Wallet = Depends(get_current_wallet),
    db: Session = Depends(get_db),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> TransactionListResponse:
    page = list_transactions(db, wallet.id, limit=limit, cursor=cursor)
    return TransactionListResponse(
        data=[
            LedgerEntryResponse(
                id=entry.id,
                entry_type=entry.entry_type,
                amount_microdollars=entry.amount_microdollars,
                balance_after_microdollars=entry.balance_after_microdollars,
                created_at=entry.created_at,
            )
            for entry in page.entries
        ],
        next_cursor=page.next_cursor,
    )
