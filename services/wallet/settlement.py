"""Batch settlement — Phase 7 (Stripe Connect payouts).

Aggregates uncleared ``usage_events`` per partner, reserves them against a
``settlement_batches`` row, issues a single Stripe Connect transfer per partner
per run, and reconciles the batch to ``cleared`` with an append-only
``ledger_entries`` settlement row on the platform wallet. Idempotent end-to-end:
``settlement_batches.idempotency_key`` is unique per partner/day, the Stripe
transfer uses the same idempotency key, and ``usage_events.settlement_status``
gating guarantees no event is ever paid twice.

Stripe is injectable (``stripe_client``) so the full flow is unit-testable with
a shim and no network. The orchestrator is embeddable (``run_settlement_once``
used in tests and the scheduler) and runnable standalone
(``python -m services.wallet.settlement``).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

import stripe
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from services.shared.config import get_settings
from services.shared.models import (
    LedgerEntry,
    PartnerAccount,
    SettlementBatch,
    UsageEvent,
    User,
    Wallet,
)

logger = logging.getLogger(__name__)

SETTLEMENT_IDEMPOTENCY_PREFIX = "settle:"
PLATFORM_USER_EMAIL = "platform@ai-wallet.internal"


class SettlementError(Exception):
    """Raised when a payout transfer fails."""


@dataclass(frozen=True)
class SettlementAggregate:
    event_count: int
    gross_usage_microdollars: int
    platform_fee_microdollars: int
    partner_payout_microdollars: int
    provider_cost_microdollars: int
    partner_margin_microdollars: int
    earliest_created_at: datetime | None
    latest_created_at: datetime | None

    @property
    def is_empty(self) -> bool:
        return self.event_count == 0


@dataclass(frozen=True)
class TransferResult:
    stripe_transfer_id: str


@dataclass
class PartnerSettlementResult:
    partner_account_id: UUID
    partner_slug: str
    status: str  # cleared | failed | skipped_empty | skipped_no_connect | skipped_below_threshold
    batch: SettlementBatch | None = None
    error: str | None = None
    event_count: int = 0
    payout_microdollars: int = 0


@dataclass
class SettlementRunReport:
    started_at: datetime
    finished_at: datetime
    results: list[PartnerSettlementResult] = field(default_factory=list)

    @property
    def cleared(self) -> list[PartnerSettlementResult]:
        return [r for r in self.results if r.status == "cleared"]

    @property
    def failed(self) -> list[PartnerSettlementResult]:
        return [r for r in self.results if r.status == "failed"]


# ---------------------------------------------------------------------------
# Platform wallet (master pool ledger anchor)
# ---------------------------------------------------------------------------


def get_or_create_platform_wallet(session: Session) -> Wallet:
    """Return the dedicated platform wallet that anchors settlement ledger rows.

    The platform wallet is a virtual scoreboard anchor for payout audit rows;
    its balance is not the real master-pool balance and is never debited through
    the normal user-wallet path. The settlement ledger row records the payout
    amount as an append-only audit entry without mutating the balance.
    """
    settings = get_settings()
    if settings.settlement_platform_wallet_id:
        wallet = session.get(Wallet, UUID(settings.settlement_platform_wallet_id))
        if wallet is not None:
            return wallet

    user = session.scalar(select(User).where(User.email == PLATFORM_USER_EMAIL))
    if user is None:
        user = User(
            email=PLATFORM_USER_EMAIL,
            display_name="AI Wallet Platform",
            email_verified_at=datetime.now(UTC),
        )
        session.add(user)
        session.flush()

    wallet = session.scalar(select(Wallet).where(Wallet.user_id == user.id))
    if wallet is None:
        wallet = Wallet(user_id=user.id, balance_microdollars=0)
        session.add(wallet)
        session.flush()
    return wallet


# ---------------------------------------------------------------------------
# Aggregation + reservation
# ---------------------------------------------------------------------------


def aggregate_pending(
    session: Session, partner_account_id: UUID, *, period_end: datetime | None = None
) -> SettlementAggregate:
    """Sum pending completed usage events for a partner (no mutation)."""
    end = period_end or datetime.now(UTC)
    settings = get_settings()
    lookback_days = settings.settlement_lookback_days
    stmt = select(
        func.count().label("count"),
        func.coalesce(func.sum(UsageEvent.charged_microdollars), 0).label("gross"),
        func.coalesce(func.sum(UsageEvent.platform_fee_microdollars), 0).label("fee"),
        func.coalesce(func.sum(UsageEvent.base_cost_microdollars), 0).label("provider"),
        func.coalesce(func.sum(UsageEvent.partner_margin_microdollars), 0).label("margin"),
        func.min(UsageEvent.created_at).label("earliest"),
        func.max(UsageEvent.created_at).label("latest"),
    ).where(
        UsageEvent.partner_account_id == partner_account_id,
        UsageEvent.settlement_status == "pending",
        UsageEvent.status == "completed",
        UsageEvent.created_at < end,
    )
    if lookback_days and lookback_days > 0:
        stmt = stmt.where(UsageEvent.created_at >= end - timedelta(days=lookback_days))

    row = session.execute(stmt).one()
    gross = int(row.gross or 0)
    fee = int(row.fee or 0)
    provider = int(row.provider or 0)
    margin = int(row.margin or 0)
    return SettlementAggregate(
        event_count=int(row.count or 0),
        gross_usage_microdollars=gross,
        platform_fee_microdollars=fee,
        partner_payout_microdollars=gross - fee,
        provider_cost_microdollars=provider,
        partner_margin_microdollars=margin,
        earliest_created_at=row.earliest,
        latest_created_at=row.latest,
    )


def _existing_batch(session: Session, idempotency_key: str) -> SettlementBatch | None:
    return session.scalar(
        select(SettlementBatch).where(SettlementBatch.idempotency_key == idempotency_key)
    )


def create_batch(
    session: Session,
    *,
    partner_account_id: UUID,
    period_start: datetime,
    period_end: datetime,
    idempotency_key: str,
) -> SettlementBatch:
    """Idempotent batch creation. Returns existing row on a repeat key."""
    existing = _existing_batch(session, idempotency_key)
    if existing is not None:
        return existing
    batch = SettlementBatch(
        partner_account_id=partner_account_id,
        period_start=period_start,
        period_end=period_end,
        idempotency_key=idempotency_key,
    )
    session.add(batch)
    session.flush()
    return batch


def reserve_events(session: Session, batch: SettlementBatch) -> int:
    """Atomically claim pending events for this batch and recompute batch totals.

    Returns the total number of reserved events now attached to the batch
    (including ones claimed by a previous run that crashed before reconcile).
    """
    claim_stmt = (
        update(UsageEvent)
        .where(
            UsageEvent.partner_account_id == batch.partner_account_id,
            UsageEvent.settlement_status == "pending",
            UsageEvent.status == "completed",
            UsageEvent.created_at < batch.period_end,
        )
        .values(settlement_status="reserved", settlement_batch_id=batch.id)
        .returning(UsageEvent.id)
    )
    list(session.execute(claim_stmt).scalars())

    totals = session.execute(
        select(
            func.count().label("count"),
            func.coalesce(func.sum(UsageEvent.charged_microdollars), 0).label("gross"),
            func.coalesce(func.sum(UsageEvent.platform_fee_microdollars), 0).label("fee"),
            func.coalesce(func.sum(UsageEvent.base_cost_microdollars), 0).label("provider"),
            func.coalesce(func.sum(UsageEvent.partner_margin_microdollars), 0).label("margin"),
            func.min(UsageEvent.created_at).label("earliest"),
            func.max(UsageEvent.created_at).label("latest"),
            func.array_agg(UsageEvent.id).label("ids"),
        ).where(
            UsageEvent.settlement_batch_id == batch.id,
            UsageEvent.settlement_status == "reserved",
        )
    ).one()

    count = int(totals.count or 0)
    gross = int(totals.gross or 0)
    fee = int(totals.fee or 0)
    batch.event_count = count
    batch.gross_usage_microdollars = gross
    batch.platform_fee_microdollars = fee
    batch.partner_payout_microdollars = gross - fee
    batch.provider_cost_microdollars = int(totals.provider or 0)
    batch.partner_margin_microdollars = int(totals.margin or 0)
    batch.reserved_event_ids = list(totals.ids or [])
    # period_end stays as the run cutoff so re-claims after a failed attempt still
    # match the same events; only narrow period_start to the earliest reserved event.
    if totals.earliest is not None and (
        batch.period_start is None or totals.earliest < batch.period_start
    ):
        batch.period_start = totals.earliest
    session.flush()
    return count


def release_reserved(session: Session, batch_id: UUID) -> None:
    """Return reserved events for a failed batch back to pending (re-attemptable)."""
    session.execute(
        update(UsageEvent)
        .where(
            UsageEvent.settlement_batch_id == batch_id,
            UsageEvent.settlement_status == "reserved",
        )
        .values(settlement_status="pending", settlement_batch_id=None)
    )
    session.flush()


# ---------------------------------------------------------------------------
# Stripe transfer
# ---------------------------------------------------------------------------


def _microdollars_to_stripe_cents(amount_microdollars: int) -> int:
    return amount_microdollars // 10_000


def _configure_stripe() -> None:
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise RuntimeError("Stripe is not configured")
    stripe.api_key = settings.stripe_secret_key


def execute_transfer(
    batch: SettlementBatch,
    partner: PartnerAccount,
    *,
    stripe_client=None,
) -> TransferResult:
    """Issue a single Stripe Connect transfer for the batch payout."""
    if not partner.stripe_connect_id:
        raise SettlementError(f"partner {partner.slug} has no stripe_connect_id")
    payout_cents = _microdollars_to_stripe_cents(batch.partner_payout_microdollars)
    if payout_cents <= 0:
        raise SettlementError(f"payout for batch {batch.id} is non-positive")

    client = stripe_client if stripe_client is not None else stripe
    if stripe_client is None:
        _configure_stripe()

    transfer = client.Transfer.create(
        amount=payout_cents,
        currency="usd",
        destination=partner.stripe_connect_id,
        metadata={
            "settlement_batch_id": str(batch.id),
            "partner_account_id": str(partner.id),
            "partner_slug": partner.slug,
            "event_count": str(batch.event_count),
            "gross_usage_microdollars": str(batch.gross_usage_microdollars),
            "platform_fee_microdollars": str(batch.platform_fee_microdollars),
            "partner_payout_microdollars": str(batch.partner_payout_microdollars),
        },
        idempotency_key=batch.idempotency_key,
    )
    return TransferResult(stripe_transfer_id=transfer.id)


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


def reconcile_cleared(
    session: Session,
    batch: SettlementBatch,
    *,
    stripe_transfer_id: str,
) -> SettlementBatch:
    """Mark a batch cleared, flip reserved events to cleared, write the audit row."""
    platform_wallet = get_or_create_platform_wallet(session)

    existing_entry = session.scalar(
        select(LedgerEntry).where(
            LedgerEntry.wallet_id == platform_wallet.id,
            LedgerEntry.idempotency_key == f"settlement:{batch.id}",
        )
    )
    if existing_entry is None:
        entry = LedgerEntry(
            wallet_id=platform_wallet.id,
            entry_type="settlement",
            amount_microdollars=batch.partner_payout_microdollars,
            balance_after_microdollars=platform_wallet.balance_microdollars,
            idempotency_key=f"settlement:{batch.id}",
            reference_type="settlement_batch",
            reference_id=batch.id,
            metadata_json={
                "partner_account_id": str(batch.partner_account_id),
                "stripe_transfer_id": stripe_transfer_id,
                "gross_usage_microdollars": batch.gross_usage_microdollars,
                "platform_fee_microdollars": batch.platform_fee_microdollars,
                "partner_payout_microdollars": batch.partner_payout_microdollars,
                "provider_cost_microdollars": batch.provider_cost_microdollars,
                "partner_margin_microdollars": batch.partner_margin_microdollars,
                "event_count": batch.event_count,
            },
        )
        session.add(entry)
        session.flush()
        batch.ledger_entry_id = entry.id

    batch.status = "cleared"
    batch.stripe_transfer_id = stripe_transfer_id
    batch.cleared_at = datetime.now(UTC)
    batch.updated_at = datetime.now(UTC)
    session.flush()

    session.execute(
        update(UsageEvent)
        .where(
            UsageEvent.settlement_batch_id == batch.id,
            UsageEvent.settlement_status == "reserved",
        )
        .values(settlement_status="cleared")
    )
    session.flush()
    return batch


def mark_failed(
    session: Session, batch: SettlementBatch, error_message: str
) -> SettlementBatch:
    """Mark a batch failed and release its reserved events back to pending."""
    batch.status = "failed"
    batch.error_message = error_message
    batch.updated_at = datetime.now(UTC)
    session.flush()
    release_reserved(session, batch.id)
    return batch


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def _eligible_partners(
    session: Session, *, partner_slug: str | None = None
) -> list[PartnerAccount]:
    stmt = select(PartnerAccount).where(PartnerAccount.status == "active")
    if partner_slug is not None:
        stmt = stmt.where(PartnerAccount.slug == partner_slug)
    return list(session.scalars(stmt).all())


def settle_partner(
    session: Session,
    partner: PartnerAccount,
    *,
    period_end: datetime | None = None,
    stripe_client=None,
) -> PartnerSettlementResult:
    """Settle one partner end-to-end. Caller owns the transaction."""
    settings = get_settings()
    end = period_end or datetime.now(UTC)
    run_key = end.date().isoformat()
    idem_key = f"{SETTLEMENT_IDEMPOTENCY_PREFIX}{partner.id}:{run_key}"

    if not partner.stripe_connect_id:
        return PartnerSettlementResult(
            partner_account_id=partner.id,
            partner_slug=partner.slug,
            status="skipped_no_connect",
        )

    existing = _existing_batch(session, idem_key)
    if existing is not None and existing.status == "cleared":
        return PartnerSettlementResult(
            partner_account_id=partner.id,
            partner_slug=partner.slug,
            status="cleared",
            batch=existing,
            event_count=existing.event_count,
            payout_microdollars=existing.partner_payout_microdollars,
        )

    if existing is None:
        aggregate = aggregate_pending(session, partner.id, period_end=end)
        if aggregate.is_empty:
            return PartnerSettlementResult(
                partner_account_id=partner.id,
                partner_slug=partner.slug,
                status="skipped_empty",
            )
        if aggregate.partner_payout_microdollars < settings.settlement_min_payout_microdollars:
            return PartnerSettlementResult(
                partner_account_id=partner.id,
                partner_slug=partner.slug,
                status="skipped_below_threshold",
                event_count=aggregate.event_count,
                payout_microdollars=aggregate.partner_payout_microdollars,
            )

    batch = create_batch(
        session,
        partner_account_id=partner.id,
        period_start=end - timedelta(days=settings.settlement_lookback_days or 0),
        period_end=end,
        idempotency_key=idem_key,
    )

    if batch.status == "failed":
        release_reserved(session, batch.id)
        batch.status = "pending"
        batch.error_message = None
        session.flush()

    reserved_count = reserve_events(session, batch)
    if reserved_count == 0 and not batch.reserved_event_ids:
        # Nothing to claim (e.g. a concurrent run beat us); remove the stub batch.
        session.delete(batch)
        session.flush()
        return PartnerSettlementResult(
            partner_account_id=partner.id,
            partner_slug=partner.slug,
            status="skipped_empty",
        )

    try:
        transfer = execute_transfer(batch, partner, stripe_client=stripe_client)
    except Exception as exc:  # noqa: BLE001 — payout failure is recoverable
        logger.exception("settlement transfer failed for partner %s: %s", partner.slug, exc)
        mark_failed(session, batch, str(exc))
        return PartnerSettlementResult(
            partner_account_id=partner.id,
            partner_slug=partner.slug,
            status="failed",
            batch=batch,
            error=str(exc),
            event_count=batch.event_count,
            payout_microdollars=batch.partner_payout_microdollars,
        )

    reconcile_cleared(session, batch, stripe_transfer_id=transfer.stripe_transfer_id)
    logger.info(
        "settlement cleared partner=%s events=%s gross=%s fee=%s payout=%s transfer=%s",
        partner.slug,
        batch.event_count,
        batch.gross_usage_microdollars,
        batch.platform_fee_microdollars,
        batch.partner_payout_microdollars,
        transfer.stripe_transfer_id,
    )
    return PartnerSettlementResult(
        partner_account_id=partner.id,
        partner_slug=partner.slug,
        status="cleared",
        batch=batch,
        event_count=batch.event_count,
        payout_microdollars=batch.partner_payout_microdollars,
    )


def run_settlement_once(
    session_factory=None,
    *,
    session: Session | None = None,
    partner_slug: str | None = None,
    stripe_client=None,
    now: datetime | None = None,
) -> SettlementRunReport:
    """Run one settlement sweep across eligible partners. Used in tests + scheduler.

    Pass ``session`` to settle within a caller-owned transaction (tests); omit
    it to open/commit/close a transaction per partner via ``session_factory``.
    """
    started = datetime.now(UTC)
    end = now or datetime.now(UTC)
    results: list[PartnerSettlementResult] = []

    if session is not None:
        partners = _eligible_partners(session, partner_slug=partner_slug)
        for partner in partners:
            results.append(
                settle_partner(session, partner, period_end=end, stripe_client=stripe_client)
            )
            session.flush()
    else:
        factory = session_factory or _default_factory()
        partners_loaded = False
        while not partners_loaded:
            with _session_scope(factory) as sess:
                partners = _eligible_partners(sess, partner_slug=partner_slug)
                partners_loaded = True
            for partner in partners:
                with _session_scope(factory) as sess:
                    refreshed = sess.get(PartnerAccount, partner.id)
                    if refreshed is None:
                        continue
                    results.append(
                        settle_partner(
                            sess, refreshed, period_end=end, stripe_client=stripe_client
                        )
                    )

    return SettlementRunReport(
        started_at=started,
        finished_at=datetime.now(UTC),
        results=results,
    )


def list_settlement_batches(
    session: Session,
    partner_account_id: UUID | None = None,
    *,
    limit: int = 20,
) -> list[SettlementBatch]:
    limit = min(max(limit, 1), 100)
    stmt = select(SettlementBatch).order_by(SettlementBatch.created_at.desc()).limit(limit)
    if partner_account_id is not None:
        stmt = stmt.where(SettlementBatch.partner_account_id == partner_account_id)
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------


def run_settlement_loop(session_factory=None, *, interval_seconds: float | None = None) -> None:
    """Poll-and-sleep loop. The scheduler uses next-UTC-midnight timing instead."""
    import time

    factory = session_factory or _default_factory()
    logger.info("settlement loop started")
    while True:
        try:
            run_settlement_once(factory)
        except Exception as exc:  # noqa: BLE001
            logger.exception("settlement loop error: %s", exc)
        time.sleep(interval_seconds or 3600.0)


def _default_factory():
    from services.shared.db import get_session_factory

    return get_session_factory()


@contextmanager
def _session_scope(factory: sessionmaker[Session]):
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    from services.shared.logging import configure_logging

    settings = get_settings()
    configure_logging(settings.log_level, settings.app_env)
    report = run_settlement_once()
    logger.info(
        "settlement run complete: %d cleared, %d failed, %d skipped",
        len(report.cleared),
        len(report.failed),
        len(report.results) - len(report.cleared) - len(report.failed),
    )


if __name__ == "__main__":
    main()
