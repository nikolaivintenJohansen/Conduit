"""Billing worker — the slow path (Phase 4 / Phase 5).

Drains the usage-event stream (``services/gateway/usage_queue.py``), rates each
event (base provider cost + partner markup + platform fee), and writes the
immutable ledger row + ``UsageEvent`` row in a single DB transaction. Holds
placed on the Redis fast path are released against the cached balance
projection; holds that fell back to a DB row are settled via ``settle_usage``.

The worker is intentionally embeddable: ``run_once()`` drains one batch
synchronously (used in tests and the lifespan task), and ``run_loop()`` polls
forever for production. Run standalone with ``python -m services.gateway.worker``.

Idempotency: ``UsageEvent.request_id`` is unique and ``ledger_entries`` has a
unique ``(wallet_id, idempotency_key)`` constraint, so redelivered stream
entries are no-ops. Successfully processed entries are XACK'd and XDEL'd; failed
entries are logged and left un-acked for retry. After
``worker_max_delivery_attempts`` deliveries a poison entry is moved to the
dead-letter stream (``conduit:usage:dlq``) instead of being retried forever, and
``claim_stale`` reclaims entries stranded by a dead consumer. The worker also
keeps the Redis ``monthly_spent`` projection in sync (``incr_monthly_spent``)
and runs a bounded balance-cache revalidation sweep in ``run_loop``.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from services.gateway import allowance_cache, balance_cache, usage_queue
from services.gateway.mock_provider import estimate_base_cost
from services.pricing.engine import calculate_charge
from services.shared.config import get_settings
from services.shared.models import AppInstall, BalanceHold, ModelCatalog, VirtualKey
from services.wallet.ledger import get_wallet_by_user_id
from services.wallet.usage import settle_usage, settle_usage_direct

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerStats:
    processed: int
    settled: int
    skipped: int
    failed: int


def _parse_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _resolve_model_id(session: Session, model_slug: str) -> UUID | None:
    return session.scalar(
        select(ModelCatalog.id).where(
            ModelCatalog.slug == model_slug, ModelCatalog.is_active.is_(True)
        )
    )


def settle_event(session: Session, fields: dict) -> bool:
    """Settle one usage event. Returns True if a new ledger row was written."""
    request_id = fields["request_id"]
    user_id = _parse_uuid(fields.get("user_id"))
    wallet_id = _parse_uuid(fields.get("wallet_id"))
    model = fields["model"]
    input_tokens = int(fields.get("input_tokens", 0))
    output_tokens = int(fields.get("output_tokens", 0))
    provider = fields.get("provider") or None
    virtual_key_id = _parse_uuid(fields.get("virtual_key_id"))
    partner_account_id = _parse_uuid(fields.get("partner_account_id"))
    app_install_id = _parse_uuid(fields.get("app_install_id"))
    estimated_held = int(fields.get("estimated_max_microdollars", 0))

    if user_id is None:
        logger.warning("usage event %s missing user_id", request_id)
        return False

    if wallet_id is None:
        wallet = get_wallet_by_user_id(session, user_id)
        if wallet is None:
            logger.warning("usage event %s has no wallet for user %s", request_id, user_id)
            return False
        wallet_id = wallet.id

    model_id = _resolve_model_id(session, model)
    base_cost = estimate_base_cost(model, input_tokens, output_tokens)
    pricing = calculate_charge(
        session,
        base_cost_microdollars=base_cost,
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        partner_account_id=partner_account_id,
    )

    virtual_key = (
        session.get(VirtualKey, virtual_key_id) if virtual_key_id is not None else None
    )

    settle_metadata = {}
    if app_install_id is not None:
        settle_metadata["app_install_id"] = str(app_install_id)

    db_hold: BalanceHold | None = session.scalar(
        select(BalanceHold).where(BalanceHold.request_id == request_id)
    )

    if db_hold is not None:
        # Sync fallback path: settle the DB hold (releases held, debits actual).
        result = settle_usage(
            session,
            request_id=request_id,
            user_id=user_id,
            wallet_id=wallet_id,
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            base_cost_microdollars=pricing.base_cost_microdollars,
            charged_microdollars=pricing.charged_microdollars,
            platform_fee_microdollars=pricing.platform_fee_microdollars,
            partner_margin_microdollars=pricing.partner_margin_microdollars,
            partner_account_id=partner_account_id,
            virtual_key_id=virtual_key_id,
            latency_ms=None,
            virtual_key=virtual_key,
            metadata=settle_metadata,
        )
        created = result.created
    else:
        # Redis fast path: direct debit (hold was in Redis, not Postgres).
        result = settle_usage_direct(
            session,
            request_id=request_id,
            user_id=user_id,
            wallet_id=wallet_id,
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            base_cost_microdollars=pricing.base_cost_microdollars,
            charged_microdollars=pricing.charged_microdollars,
            platform_fee_microdollars=pricing.platform_fee_microdollars,
            partner_margin_microdollars=pricing.partner_margin_microdollars,
            partner_account_id=partner_account_id,
            virtual_key_id=virtual_key_id,
            latency_ms=None,
            virtual_key=virtual_key,
            metadata=settle_metadata,
        )
        created = result.created
        # Release the Redis-side hold projection against the cached balance.
        if created and estimated_held > 0:
            balance_cache.release_hold(
                wallet_id, request_id, estimated_held, pricing.charged_microdollars
            )

    # App-scoped: increment the authoritative per-app allowance + Redis projection.
    if created and app_install_id is not None:
        install = session.get(AppInstall, app_install_id, with_for_update=True)
        if install is not None and install.revoked_at is None:
            install.allowance_spent_microdollars += pricing.charged_microdollars
            session.flush()
            allowance_cache.increment_allowance_spent(
                app_install_id, pricing.charged_microdollars
            )

    # Keep the Redis monthly-spend projection in sync so the fast-path Lua can
    # enforce the wallet monthly spend limit without a DB hit (Phase 5 hardening).
    if created and pricing.charged_microdollars > 0:
        balance_cache.incr_monthly_spent(wallet_id, pricing.charged_microdollars)

    if virtual_key is not None and created:
        from datetime import UTC, datetime

        virtual_key.last_used_at = datetime.now(UTC)

    return created


def run_once(
    session_factory=None,
    *,
    session: Session | None = None,
    consumer: str | None = None,
    count: int | None = None,
    claim_idle_ms: int | None = None,
) -> WorkerStats:
    """Drain one batch from the stream and settle it. Used in tests + lifespan.

    Pass ``session`` to settle within a caller-owned transaction (tests); omit
    it to open/commit/close a transaction per event via ``session_factory``.
    ``claim_idle_ms`` overrides the stale-pending reclaim threshold (tests use
    ``0`` to force immediate re-delivery of un-acked entries).
    """
    settings = get_settings()
    usage_queue.ensure_consumer_group()
    # Reclaim entries stranded by a dead consumer before reading new ones.
    claimed = usage_queue.claim_stale(consumer=consumer, idle_ms=claim_idle_ms)
    batch = claimed + usage_queue.read_batch(consumer=consumer, count=count, block_ms=0)
    if not batch:
        return WorkerStats(processed=0, settled=0, skipped=0, failed=0)

    processed = settled = skipped = failed = 0
    factory = session_factory or _default_factory()
    for entry_id, fields in batch:
        processed += 1
        attempts = usage_queue.incr_attempt(entry_id)
        if attempts > settings.worker_max_delivery_attempts:
            usage_queue.move_to_dlq(entry_id, fields, "max_delivery_attempts")
            failed += 1
            logger.warning(
                "usage event %s moved to DLQ after %s attempts", entry_id, attempts
            )
            continue
        try:
            if session is not None:
                created = settle_event(session, fields)
                session.flush()
            else:
                with _session_scope(factory) as sess:
                    created = settle_event(sess, fields)
            if created:
                settled += 1
            else:
                skipped += 1
            usage_queue.ack_event(entry_id)
            usage_queue.delete_event(entry_id)
            usage_queue.clear_attempt(entry_id)
        except Exception as exc:  # noqa: BLE001 — worker must not die on a bad event
            failed += 1
            logger.exception("failed to settle usage event %s: %s", entry_id, exc)
    return WorkerStats(processed=processed, settled=settled, skipped=skipped, failed=failed)


def run_loop(session_factory=None) -> None:
    """Poll the stream forever. Production entry point."""
    settings = get_settings()
    factory = session_factory or _default_factory()
    usage_queue.ensure_consumer_group()
    logger.info(
        "billing worker started (stream=%s group=%s)",
        settings.usage_stream_name,
        settings.usage_consumer_group,
    )
    revalidate_interval_s = settings.balance_cache_revalidate_interval_ms / 1000.0
    last_revalidate = 0.0
    while True:
        try:
            stats = run_once(factory, count=settings.worker_max_batch)
            now = time.time()
            if revalidate_interval_s > 0 and (now - last_revalidate) >= revalidate_interval_s:
                with _session_scope(factory) as sess:
                    balance_cache.revalidate_sweep(sess)
                last_revalidate = now
            if stats.processed == 0:
                time.sleep(settings.worker_poll_ms / 1000.0)
        except Exception as exc:  # noqa: BLE001
            logger.exception("worker loop error: %s", exc)
            time.sleep(settings.worker_poll_ms / 1000.0)


def _default_factory():
    from services.shared.db import get_session_factory

    return get_session_factory()


@contextmanager
def _session_scope(factory: sessionmaker[Session]):
    """Open/commit/close one worker transaction against ``factory``."""
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
    run_loop()


if __name__ == "__main__":
    main()
