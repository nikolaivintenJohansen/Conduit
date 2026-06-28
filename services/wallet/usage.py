import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.shared.models import BalanceHold, LedgerEntry, UsageEvent, VirtualKey
from services.wallet.balance import SettleResult, settle_hold
from services.wallet.ledger import (
    LedgerResult,
    debit_wallet,
    get_wallet,
    monthly_spend_microdollars,
)

logger = logging.getLogger(__name__)


def _tag_spend_limit_overage(session: Session, usage_event: UsageEvent, wallet_id: UUID) -> None:
    """Soft overage check on the async settle path (Phase 5 hardening).

    The hold already reserved funds and the tokens are already consumed, so the
    debit must stand to keep the ledger correct. This only *observes* that the
    wallet's monthly spend limit was exceeded and tags the usage event so Phase 7
    settlement / alerting can surface it. No-op when no limit is configured.
    """
    wallet = get_wallet(session, wallet_id)
    if wallet is None or wallet.spend_limit_microdollars is None:
        return
    spent = monthly_spend_microdollars(session, wallet_id)
    if spent > wallet.spend_limit_microdollars:
        logger.warning(
            "spend_limit_overage wallet=%s request_id=%s spent=%s limit=%s",
            wallet_id,
            usage_event.request_id,
            spent,
            wallet.spend_limit_microdollars,
        )
        metadata = dict(usage_event.metadata_json or {})
        metadata["spend_limit_overage"] = True
        metadata["spend_limit_microdollars"] = int(wallet.spend_limit_microdollars)
        metadata["monthly_spend_microdollars"] = int(spent)
        usage_event.metadata_json = metadata


@dataclass(frozen=True)
class SettleUsageResult:
    usage_event: UsageEvent
    settle_result: SettleResult
    created: bool


@dataclass(frozen=True)
class UsagePage:
    events: list[UsageEvent]
    next_cursor: str | None


def get_usage_event_by_request_id(session: Session, request_id: str) -> UsageEvent | None:
    return session.scalar(select(UsageEvent).where(UsageEvent.request_id == request_id))


def settle_usage(
    session: Session,
    *,
    request_id: str,
    user_id: UUID,
    wallet_id: UUID,
    model: str,
    input_tokens: int,
    output_tokens: int,
    base_cost_microdollars: int,
    charged_microdollars: int,
    platform_fee_microdollars: int = 0,
    partner_margin_microdollars: int = 0,
    provider: str | None = None,
    virtual_key_id: UUID | None = None,
    partner_account_id: UUID | None = None,
    latency_ms: int | None = None,
    status: str = "completed",
    metadata: dict | None = None,
    virtual_key: VirtualKey | None = None,
) -> SettleUsageResult:
    existing = get_usage_event_by_request_id(session, request_id)
    if existing:
        debit_entry = session.scalar(
            select(LedgerEntry).where(
                LedgerEntry.wallet_id == wallet_id,
                LedgerEntry.idempotency_key == f"settle:{request_id}",
            )
        )
        hold = session.scalar(select(BalanceHold).where(BalanceHold.request_id == request_id))
        release_entry = session.scalar(
            select(LedgerEntry).where(
                LedgerEntry.wallet_id == wallet_id,
                LedgerEntry.idempotency_key == f"hold_release:{request_id}",
            )
        )
        assert hold is not None and debit_entry is not None and release_entry is not None
        wallet = get_wallet(session, wallet_id)
        assert wallet is not None
        return SettleUsageResult(
            usage_event=existing,
            settle_result=SettleResult(
                hold=hold,
                debit=LedgerResult(debit_entry, wallet, False),
                release_entry=release_entry,
            ),
            created=False,
        )

    usage_event = UsageEvent(
        request_id=request_id,
        user_id=user_id,
        virtual_key_id=virtual_key_id,
        wallet_id=wallet_id,
        model=model,
        provider=provider,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        base_cost_microdollars=base_cost_microdollars,
        charged_microdollars=charged_microdollars,
        platform_fee_microdollars=platform_fee_microdollars,
        partner_margin_microdollars=partner_margin_microdollars,
        partner_account_id=partner_account_id,
        latency_ms=latency_ms,
        status=status,
        metadata_json=metadata or {},
    )
    session.add(usage_event)
    session.flush()

    settle_result = settle_hold(
        session,
        request_id,
        charged_microdollars,
        reference_type="usage_event",
        reference_id=usage_event.id,
        metadata={
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            **(metadata or {}),
        },
        virtual_key=virtual_key,
    )

    _tag_spend_limit_overage(session, usage_event, wallet_id)

    return SettleUsageResult(
        usage_event=usage_event,
        settle_result=settle_result,
        created=True,
    )


def settle_usage_direct(
    session: Session,
    *,
    request_id: str,
    user_id: UUID,
    wallet_id: UUID,
    model: str,
    input_tokens: int,
    output_tokens: int,
    base_cost_microdollars: int,
    charged_microdollars: int,
    platform_fee_microdollars: int = 0,
    partner_margin_microdollars: int = 0,
    provider: str | None = None,
    virtual_key_id: UUID | None = None,
    partner_account_id: UUID | None = None,
    latency_ms: int | None = None,
    status: str = "completed",
    metadata: dict | None = None,
    virtual_key: VirtualKey | None = None,
) -> SettleUsageResult:
    """Settle a usage event that was pre-authorized on the Redis fast path.

    Unlike ``settle_usage`` (which settles an existing DB ``BalanceHold``), this
    path performs a direct debit — the hold lived in Redis and was released by
    the caller (``balance_cache.release_hold``). Idempotent on ``request_id``:
    a repeated event returns the existing rows with ``created=False``.
    """
    existing = get_usage_event_by_request_id(session, request_id)
    if existing:
        wallet = get_wallet(session, wallet_id)
        assert wallet is not None
        debit_entry = session.scalar(
            select(LedgerEntry).where(
                LedgerEntry.wallet_id == wallet_id,
                LedgerEntry.idempotency_key == f"settle:{request_id}",
            )
        )
        assert debit_entry is not None
        return SettleUsageResult(
            usage_event=existing,
            settle_result=SettleResult(
                hold=None,  # type: ignore[arg-type]
                debit=LedgerResult(debit_entry, wallet, False),
                release_entry=None,  # type: ignore[arg-type]
            ),
            created=False,
        )

    usage_event = UsageEvent(
        request_id=request_id,
        user_id=user_id,
        virtual_key_id=virtual_key_id,
        wallet_id=wallet_id,
        model=model,
        provider=provider,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        base_cost_microdollars=base_cost_microdollars,
        charged_microdollars=charged_microdollars,
        platform_fee_microdollars=platform_fee_microdollars,
        partner_margin_microdollars=partner_margin_microdollars,
        partner_account_id=partner_account_id,
        latency_ms=latency_ms,
        status=status,
        metadata_json=metadata or {},
    )
    session.add(usage_event)
    session.flush()

    debit_result = debit_wallet(
        session,
        wallet_id,
        charged_microdollars,
        idempotency_key=f"settle:{request_id}",
        reference_type="usage_event",
        reference_id=usage_event.id,
        metadata={
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            **(metadata or {}),
        },
        virtual_key=virtual_key,
        skip_spend_limit_check=True,
    )

    _tag_spend_limit_overage(session, usage_event, wallet_id)

    return SettleUsageResult(
        usage_event=usage_event,
        settle_result=SettleResult(
            hold=None,  # type: ignore[arg-type]
            debit=debit_result,
            release_entry=None,  # type: ignore[arg-type]
        ),
        created=True,
    )


def list_usage_events(
    session: Session,
    user_id: UUID,
    *,
    limit: int = 20,
    cursor: str | None = None,
) -> UsagePage:
    limit = min(max(limit, 1), 100)
    stmt = (
        select(UsageEvent)
        .where(UsageEvent.user_id == user_id)
        .order_by(UsageEvent.created_at.desc(), UsageEvent.id.desc())
        .limit(limit + 1)
    )

    if cursor:
        cursor_created_at, _, cursor_id = cursor.partition("|")
        stmt = stmt.where(
            (UsageEvent.created_at < datetime.fromisoformat(cursor_created_at))
            | (
                (UsageEvent.created_at == datetime.fromisoformat(cursor_created_at))
                & (UsageEvent.id < UUID(cursor_id))
            )
        )

    events = list(session.scalars(stmt).all())
    next_cursor = None
    if len(events) > limit:
        last = events[limit - 1]
        next_cursor = f"{last.created_at.isoformat()}|{last.id}"
        events = events[:limit]

    return UsagePage(events=events, next_cursor=next_cursor)
