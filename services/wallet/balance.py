from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.shared.config import get_settings
from services.shared.models import BalanceHold, LedgerEntry, VirtualKey, Wallet
from services.wallet.ledger import (
    LedgerResult,
    debit_wallet,
    get_available_balance,
    get_or_create_wallet,
    get_wallet,
    monthly_spend_microdollars,
)


@dataclass(frozen=True)
class BalanceSummary:
    wallet_id: UUID
    balance_microdollars: int
    held_microdollars: int
    available_microdollars: int
    currency: str
    low_balance_threshold_microdollars: int
    spend_limit_microdollars: int | None
    monthly_spend_microdollars: int


@dataclass(frozen=True)
class HoldResult:
    hold: BalanceHold
    wallet: Wallet
    ledger_entry: LedgerEntry
    created: bool


@dataclass(frozen=True)
class SettleResult:
    hold: BalanceHold
    debit: LedgerResult
    release_entry: LedgerEntry


@dataclass(frozen=True)
class TransactionPage:
    entries: list[LedgerEntry]
    next_cursor: str | None


def wallet_summary(session: Session, wallet: Wallet) -> BalanceSummary:
    return BalanceSummary(
        wallet_id=wallet.id,
        balance_microdollars=wallet.balance_microdollars,
        held_microdollars=wallet.held_microdollars,
        available_microdollars=get_available_balance(wallet),
        currency=wallet.currency,
        low_balance_threshold_microdollars=wallet.low_balance_threshold_microdollars,
        spend_limit_microdollars=wallet.spend_limit_microdollars,
        monthly_spend_microdollars=monthly_spend_microdollars(session, wallet.id),
    )


def get_wallet_summary_for_user(session: Session, user_id: UUID) -> BalanceSummary:
    wallet = get_or_create_wallet(session, user_id)
    return wallet_summary(session, wallet)


def update_wallet_settings(
    session: Session,
    user_id: UUID,
    *,
    spend_limit_microdollars: int | None | object = ...,
    low_balance_threshold_microdollars: int | None | object = ...,
) -> BalanceSummary:
    wallet = get_or_create_wallet(session, user_id)
    if spend_limit_microdollars is not ...:
        if spend_limit_microdollars is not None and spend_limit_microdollars < 0:
            raise ValueError("spend limit must be non-negative")
        wallet.spend_limit_microdollars = spend_limit_microdollars
    if low_balance_threshold_microdollars is not ...:
        if (
            low_balance_threshold_microdollars is not None
            and low_balance_threshold_microdollars < 0
        ):
            raise ValueError("low balance threshold must be non-negative")
        if low_balance_threshold_microdollars is not None:
            wallet.low_balance_threshold_microdollars = low_balance_threshold_microdollars
    session.flush()
    return wallet_summary(session, wallet)


def list_transactions(
    session: Session,
    wallet_id: UUID,
    *,
    limit: int = 20,
    cursor: str | None = None,
) -> TransactionPage:
    limit = min(max(limit, 1), 100)
    stmt = (
        select(LedgerEntry)
        .where(LedgerEntry.wallet_id == wallet_id)
        .order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
        .limit(limit + 1)
    )

    if cursor:
        cursor_created_at, _, cursor_id = cursor.partition("|")
        stmt = stmt.where(
            (LedgerEntry.created_at < datetime.fromisoformat(cursor_created_at))
            | (
                (LedgerEntry.created_at == datetime.fromisoformat(cursor_created_at))
                & (LedgerEntry.id < UUID(cursor_id))
            )
        )

    entries = list(session.scalars(stmt).all())
    next_cursor = None
    if len(entries) > limit:
        last = entries[limit - 1]
        next_cursor = f"{last.created_at.isoformat()}|{last.id}"
        entries = entries[:limit]

    return TransactionPage(entries=entries, next_cursor=next_cursor)


def check_and_hold(
    session: Session,
    wallet_id: UUID,
    request_id: str,
    estimated_max_microdollars: int,
    *,
    virtual_key: VirtualKey | None = None,
) -> HoldResult:
    if estimated_max_microdollars <= 0:
        raise ValueError("estimate must be positive")

    existing_hold = session.scalar(select(BalanceHold).where(BalanceHold.request_id == request_id))
    if existing_hold:
        wallet = get_wallet(session, wallet_id)
        assert wallet is not None
        entry = session.scalar(
            select(LedgerEntry).where(
                LedgerEntry.wallet_id == wallet_id,
                LedgerEntry.idempotency_key == f"hold:{request_id}",
            )
        )
        assert entry is not None
        return HoldResult(hold=existing_hold, wallet=wallet, ledger_entry=entry, created=False)

    from services.wallet.ledger import check_spend_limits

    wallet = get_wallet(session, wallet_id, for_update=True)
    if wallet is None:
        raise ValueError("wallet not found")

    check_spend_limits(session, wallet, estimated_max_microdollars, virtual_key=virtual_key)

    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.hold_expiry_seconds)

    wallet.held_microdollars += estimated_max_microdollars
    hold = BalanceHold(
        wallet_id=wallet_id,
        request_id=request_id,
        estimated_max_microdollars=estimated_max_microdollars,
        status="active",
        expires_at=expires_at,
    )
    session.add(hold)

    entry = LedgerEntry(
        wallet_id=wallet_id,
        entry_type="hold",
        amount_microdollars=estimated_max_microdollars,
        balance_after_microdollars=wallet.balance_microdollars,
        idempotency_key=f"hold:{request_id}",
        reference_type="balance_hold",
        metadata_json={"request_id": request_id},
    )
    session.add(entry)
    session.flush()

    return HoldResult(hold=hold, wallet=wallet, ledger_entry=entry, created=True)


def release_hold(session: Session, request_id: str) -> BalanceHold | None:
    hold = session.scalar(
        select(BalanceHold).where(BalanceHold.request_id == request_id).with_for_update()
    )
    if hold is None:
        return None

    if hold.status != "active":
        return hold

    wallet = get_wallet(session, hold.wallet_id, for_update=True)
    assert wallet is not None

    wallet.held_microdollars -= hold.estimated_max_microdollars
    hold.status = "released"

    existing_release = session.scalar(
        select(LedgerEntry).where(
            LedgerEntry.wallet_id == hold.wallet_id,
            LedgerEntry.idempotency_key == f"hold_release:{request_id}",
        )
    )
    if existing_release is None:
        session.add(
            LedgerEntry(
                wallet_id=hold.wallet_id,
                entry_type="hold_release",
                amount_microdollars=hold.estimated_max_microdollars,
                balance_after_microdollars=wallet.balance_microdollars,
                idempotency_key=f"hold_release:{request_id}",
                reference_type="balance_hold",
                reference_id=hold.id,
                metadata_json={"request_id": request_id},
            )
        )

    session.flush()
    return hold


def settle_hold(
    session: Session,
    request_id: str,
    actual_microdollars: int,
    *,
    reference_type: str | None = "usage_event",
    reference_id: UUID | None = None,
    metadata: dict | None = None,
    virtual_key: VirtualKey | None = None,
) -> SettleResult:
    if actual_microdollars < 0:
        raise ValueError("actual amount must be non-negative")

    hold = session.scalar(
        select(BalanceHold).where(BalanceHold.request_id == request_id).with_for_update()
    )
    if hold is None:
        raise ValueError("hold not found")

    if hold.status == "settled":
        wallet = get_wallet(session, hold.wallet_id)
        assert wallet is not None
        debit_entry = session.scalar(
            select(LedgerEntry).where(
                LedgerEntry.wallet_id == hold.wallet_id,
                LedgerEntry.idempotency_key == f"settle:{request_id}",
            )
        )
        release_entry = session.scalar(
            select(LedgerEntry).where(
                LedgerEntry.wallet_id == hold.wallet_id,
                LedgerEntry.idempotency_key == f"hold_release:{request_id}",
            )
        )
        assert debit_entry is not None and release_entry is not None
        return SettleResult(
            hold=hold,
            debit=LedgerResult(debit_entry, wallet, False),
            release_entry=release_entry,
        )

    if hold.status != "active":
        raise ValueError(f"hold status {hold.status} cannot be settled")

    wallet = get_wallet(session, hold.wallet_id, for_update=True)
    assert wallet is not None

    wallet.held_microdollars -= hold.estimated_max_microdollars
    hold.status = "settled"
    hold.settled_at = datetime.now(UTC)

    release_entry = LedgerEntry(
        wallet_id=hold.wallet_id,
        entry_type="hold_release",
        amount_microdollars=hold.estimated_max_microdollars,
        balance_after_microdollars=wallet.balance_microdollars,
        idempotency_key=f"hold_release:{request_id}",
        reference_type="balance_hold",
        reference_id=hold.id,
        metadata_json={"request_id": request_id},
    )
    session.add(release_entry)

    debit_result = debit_wallet(
        session,
        hold.wallet_id,
        actual_microdollars,
        idempotency_key=f"settle:{request_id}",
        reference_type=reference_type,
        reference_id=reference_id,
        metadata=metadata,
        virtual_key=virtual_key,
        skip_spend_limit_check=True,
    )

    session.flush()
    return SettleResult(hold=hold, debit=debit_result, release_entry=release_entry)
