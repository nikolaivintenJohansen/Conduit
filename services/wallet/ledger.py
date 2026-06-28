from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from services.shared.models import LedgerEntry, VirtualKey, Wallet


class InsufficientBalanceError(Exception):
    pass


class SpendLimitExceededError(Exception):
    pass


@dataclass(frozen=True)
class LedgerResult:
    entry: LedgerEntry
    wallet: Wallet
    created: bool


def get_available_balance(wallet: Wallet) -> int:
    return wallet.balance_microdollars - wallet.held_microdollars


def get_wallet(session: Session, wallet_id: UUID, *, for_update: bool = False) -> Wallet | None:
    stmt = select(Wallet).where(Wallet.id == wallet_id)
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalar(stmt)


def get_wallet_by_user_id(
    session: Session, user_id: UUID, *, for_update: bool = False
) -> Wallet | None:
    stmt = select(Wallet).where(Wallet.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalar(stmt)


def get_or_create_wallet(session: Session, user_id: UUID) -> Wallet:
    wallet = get_wallet_by_user_id(session, user_id)
    if wallet is not None:
        return wallet

    wallet = Wallet(user_id=user_id)
    session.add(wallet)
    session.flush()
    return wallet


def has_sufficient_balance(wallet: Wallet, amount_microdollars: int) -> bool:
    return get_available_balance(wallet) >= amount_microdollars


def _month_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def monthly_spend_microdollars(session: Session, wallet_id: UUID) -> int:
    month_start = _month_start()
    spent = session.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_microdollars), 0)).where(
            LedgerEntry.wallet_id == wallet_id,
            LedgerEntry.entry_type == "debit",
            LedgerEntry.created_at >= month_start,
        )
    )
    return int(spent or 0)


def virtual_key_spend_microdollars(session: Session, virtual_key_id: UUID) -> int:
    key_id = str(virtual_key_id)
    spent = session.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_microdollars), 0)).where(
            LedgerEntry.entry_type == "debit",
            LedgerEntry.metadata_json["virtual_key_id"].as_string() == key_id,
        )
    )
    return int(spent or 0)


def check_spend_limits(
    session: Session,
    wallet: Wallet,
    amount_microdollars: int,
    *,
    virtual_key: VirtualKey | None = None,
) -> None:
    if not has_sufficient_balance(wallet, amount_microdollars):
        raise InsufficientBalanceError(
            f"available {get_available_balance(wallet)}, required {amount_microdollars}"
        )

    if wallet.spend_limit_microdollars is not None:
        spent = monthly_spend_microdollars(session, wallet.id)
        if spent + amount_microdollars > wallet.spend_limit_microdollars:
            raise SpendLimitExceededError(
                f"monthly spend limit {wallet.spend_limit_microdollars} exceeded"
            )

    if virtual_key is not None and virtual_key.budget_microdollars is not None:
        key_spent = virtual_key_spend_microdollars(session, virtual_key.id)
        if key_spent + amount_microdollars > virtual_key.budget_microdollars:
            raise SpendLimitExceededError(
                f"virtual key budget {virtual_key.budget_microdollars} exceeded"
            )


def _existing_entry(session: Session, wallet_id: UUID, idempotency_key: str) -> LedgerEntry | None:
    return session.scalar(
        select(LedgerEntry).where(
            LedgerEntry.wallet_id == wallet_id,
            LedgerEntry.idempotency_key == idempotency_key,
        )
    )


def credit_wallet(
    session: Session,
    wallet_id: UUID,
    amount_microdollars: int,
    idempotency_key: str,
    *,
    entry_type: str = "credit",
    reference_type: str | None = None,
    reference_id: UUID | None = None,
    metadata: dict | None = None,
) -> LedgerResult:
    if amount_microdollars <= 0:
        raise ValueError("amount must be positive")
    if entry_type not in {"credit", "refund"}:
        raise ValueError("credit entry_type must be credit or refund")

    existing = _existing_entry(session, wallet_id, idempotency_key)
    if existing:
        wallet = get_wallet(session, wallet_id)
        assert wallet is not None
        return LedgerResult(entry=existing, wallet=wallet, created=False)

    wallet = get_wallet(session, wallet_id, for_update=True)
    if wallet is None:
        raise ValueError("wallet not found")

    wallet.balance_microdollars += amount_microdollars
    entry = LedgerEntry(
        wallet_id=wallet_id,
        entry_type=entry_type,
        amount_microdollars=amount_microdollars,
        balance_after_microdollars=wallet.balance_microdollars,
        idempotency_key=idempotency_key,
        reference_type=reference_type,
        reference_id=reference_id,
        metadata_json=metadata or {},
    )
    session.add(entry)
    session.flush()
    return LedgerResult(entry=entry, wallet=wallet, created=True)


def debit_wallet(
    session: Session,
    wallet_id: UUID,
    amount_microdollars: int,
    idempotency_key: str,
    *,
    reference_type: str | None = None,
    reference_id: UUID | None = None,
    metadata: dict | None = None,
    virtual_key: VirtualKey | None = None,
    skip_spend_limit_check: bool = False,
) -> LedgerResult:
    if amount_microdollars <= 0:
        raise ValueError("amount must be positive")

    existing = _existing_entry(session, wallet_id, idempotency_key)
    if existing:
        wallet = get_wallet(session, wallet_id)
        assert wallet is not None
        return LedgerResult(entry=existing, wallet=wallet, created=False)

    wallet = get_wallet(session, wallet_id, for_update=True)
    if wallet is None:
        raise ValueError("wallet not found")

    if not skip_spend_limit_check:
        check_spend_limits(session, wallet, amount_microdollars, virtual_key=virtual_key)

    wallet.balance_microdollars -= amount_microdollars
    entry_metadata = dict(metadata or {})
    if virtual_key is not None:
        entry_metadata.setdefault("virtual_key_id", str(virtual_key.id))

    entry = LedgerEntry(
        wallet_id=wallet_id,
        entry_type="debit",
        amount_microdollars=amount_microdollars,
        balance_after_microdollars=wallet.balance_microdollars,
        idempotency_key=idempotency_key,
        reference_type=reference_type,
        reference_id=reference_id,
        metadata_json=entry_metadata,
    )
    session.add(entry)
    session.flush()
    return LedgerResult(entry=entry, wallet=wallet, created=True)


def refund_wallet(
    session: Session,
    wallet_id: UUID,
    amount_microdollars: int,
    idempotency_key: str,
    *,
    reference_type: str | None = None,
    reference_id: UUID | None = None,
    metadata: dict | None = None,
) -> LedgerResult:
    return credit_wallet(
        session,
        wallet_id,
        amount_microdollars,
        idempotency_key,
        entry_type="refund",
        reference_type=reference_type,
        reference_id=reference_id,
        metadata=metadata,
    )


def adjust_wallet(
    session: Session,
    wallet_id: UUID,
    amount_microdollars: int,
    idempotency_key: str,
    *,
    direction: str = "credit",
    reference_type: str | None = "admin",
    reference_id: UUID | None = None,
    metadata: dict | None = None,
) -> LedgerResult:
    if amount_microdollars <= 0:
        raise ValueError("amount must be positive")
    if direction not in {"credit", "debit"}:
        raise ValueError("direction must be credit or debit")

    existing = _existing_entry(session, wallet_id, idempotency_key)
    if existing:
        wallet = get_wallet(session, wallet_id)
        assert wallet is not None
        return LedgerResult(entry=existing, wallet=wallet, created=False)

    wallet = get_wallet(session, wallet_id, for_update=True)
    if wallet is None:
        raise ValueError("wallet not found")

    entry_metadata = dict(metadata or {})
    entry_metadata["direction"] = direction

    if direction == "credit":
        wallet.balance_microdollars += amount_microdollars
    else:
        if not has_sufficient_balance(wallet, amount_microdollars):
            raise InsufficientBalanceError(
                f"available {get_available_balance(wallet)}, required {amount_microdollars}"
            )
        wallet.balance_microdollars -= amount_microdollars

    entry = LedgerEntry(
        wallet_id=wallet_id,
        entry_type="adjustment",
        amount_microdollars=amount_microdollars,
        balance_after_microdollars=wallet.balance_microdollars,
        idempotency_key=idempotency_key,
        reference_type=reference_type,
        reference_id=reference_id,
        metadata_json=entry_metadata,
    )
    session.add(entry)
    session.flush()
    return LedgerResult(entry=entry, wallet=wallet, created=True)
