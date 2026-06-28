"""Fast-path pre-authorization (Phase 4).

``POST /v1/authorize`` is the SDK's entry point before an AI call. It checks the
Redis-cached balance and per-app allowance and places a micro-hold in Redis — no
PostgreSQL writes on the hot path. The actual debit happens later on the slow
path (billing worker) when the corresponding usage event is drained from the
stream.

If Redis is unavailable the fast path degrades to the existing synchronous DB
hold (``check_and_hold``) so the system stays correct; the response then carries
``mode="sync"`` so the caller knows the hold is a DB row, not a Redis entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.gateway import balance_cache
from services.gateway.access import enforce_app_allowance
from services.gateway.billing import estimate_hold_microdollars
from services.gateway.deps import GatewayCaller
from services.shared.models import BalanceHold, ModelCatalog, VirtualKey
from services.wallet.balance import HoldResult, check_and_hold
from services.wallet.ledger import (
    InsufficientBalanceError,
    SpendLimitExceededError,
    get_or_create_wallet,
    get_wallet_by_user_id,
)


@dataclass(frozen=True)
class AuthorizeResult:
    authorized: bool
    request_id: str
    mode: str  # "fast" (Redis hold) or "sync" (DB hold fallback)
    held_microdollars: int
    available_microdollars: int
    balance_microdollars: int
    expires_at_ms: int | None = None
    wallet_id: UUID | None = None


def _lookup_model_id(session: Session, model_slug: str) -> UUID | None:
    row = session.scalar(
        select(ModelCatalog.id).where(
            ModelCatalog.slug == model_slug, ModelCatalog.is_active.is_(True)
        )
    )
    return row


def authorize_request(
    session: Session,
    *,
    caller: GatewayCaller,
    request_id: str,
    model: str,
    max_tokens: int | None = None,
    requested_reserve_microdollars: int | None = None,
) -> AuthorizeResult:
    wallet = get_wallet_by_user_id(session, caller.user_id)
    if wallet is None:
        wallet = get_or_create_wallet(session, caller.user_id)

    model_id = _lookup_model_id(session, model)
    partner_account_id = caller.partner_account_id

    if requested_reserve_microdollars is not None and requested_reserve_microdollars > 0:
        estimated = requested_reserve_microdollars
    else:
        estimated = estimate_hold_microdollars(
            model,
            max_tokens=max_tokens,
            session=session,
            model_id=model_id,
            partner_account_id=partner_account_id,
        )
    estimated = max(estimated, 100_000)  # $0.10 minimum hold

    # Per-app allowance is enforced on the fast path before any balance hold.
    if caller.is_app_scoped:
        enforce_app_allowance(session, caller.app_install_id, estimated)

    # Try the Redis fast path.
    cache_state = balance_cache.get_balance_state_revalidating(session, wallet.id)
    if cache_state is not None:
        context = {
            "user_id": str(caller.user_id),
            "wallet_id": str(wallet.id),
            "model": model,
            "virtual_key_id": str(caller.virtual_key_id) if caller.virtual_key_id else "",
            "app_install_id": str(caller.app_install_id) if caller.is_app_scoped else "",
            "partner_account_id": str(partner_account_id) if partner_account_id else "",
            "model_id": str(model_id) if model_id else "",
        }
        ok, held_after, available_after, code = balance_cache.place_hold_checked(
            wallet.id, request_id, estimated, context=context
        )
        if not ok:
            if code == "spend_limit_exceeded":
                raise SpendLimitExceededError(
                    f"monthly spend limit {cache_state['spend_limit_microdollars']} exceeded"
                )
            raise InsufficientBalanceError(
                f"available {available_after}, required {estimated}"
            )
        return AuthorizeResult(
            authorized=True,
            request_id=request_id,
            mode="fast",
            held_microdollars=estimated,
            available_microdollars=available_after,
            balance_microdollars=cache_state["balance_microdollars"],
            wallet_id=wallet.id,
        )

    # Redis unavailable → fall back to the synchronous DB hold.
    virtual_key = (
        session.get(VirtualKey, caller.virtual_key_id)
        if caller.virtual_key_id is not None
        else None
    )
    hold_result: HoldResult = check_and_hold(
        session, wallet.id, request_id, estimated, virtual_key=virtual_key
    )
    hold = hold_result.hold
    return AuthorizeResult(
        authorized=True,
        request_id=request_id,
        mode="sync",
        held_microdollars=hold.estimated_max_microdollars,
        available_microdollars=hold_result.wallet.balance_microdollars
        - hold_result.wallet.held_microdollars,
        balance_microdollars=hold_result.wallet.balance_microdollars,
        expires_at_ms=int(hold.expires_at.timestamp() * 1000),
        wallet_id=wallet.id,
    )


def has_db_hold(session: Session, request_id: str) -> BalanceHold | None:
    return session.scalar(select(BalanceHold).where(BalanceHold.request_id == request_id))
