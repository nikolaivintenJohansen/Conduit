import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.gateway import allowance_cache
from services.gateway.access import (
    enforce_app_allowance,
    enforce_model_access_for_group,
)
from services.gateway.billing import estimate_hold_microdollars
from services.gateway.deps import GatewayCaller
from services.gateway.mock_provider import estimate_prompt_tokens
from services.gateway.rate_limit import check_rate_limits
from services.gateway.router import ProviderError, route_chat_completion
from services.pricing.engine import ChargeBreakdown, calculate_charge
from services.shared.models import AppInstall, ModelCatalog, VirtualKey, Wallet
from services.wallet.balance import check_and_hold, release_hold
from services.wallet.ledger import get_or_create_wallet, get_wallet_by_user_id
from services.wallet.usage import settle_usage


@dataclass(frozen=True)
class ChatCompletionResult:
    response_body: dict
    charged_microdollars: int
    balance_remaining_microdollars: int
    provider: str


def list_allowed_models(session: Session, access_group_id) -> list[ModelCatalog]:
    if access_group_id is None:
        stmt = (
            select(ModelCatalog).where(ModelCatalog.is_active.is_(True)).order_by(ModelCatalog.slug)
        )
        return list(session.scalars(stmt).all())

    from services.shared.models import AccessGroupModel

    stmt = (
        select(ModelCatalog)
        .join(AccessGroupModel, AccessGroupModel.model_id == ModelCatalog.id)
        .where(
            AccessGroupModel.access_group_id == access_group_id,
            ModelCatalog.is_active.is_(True),
        )
        .order_by(ModelCatalog.slug)
    )
    return list(session.scalars(stmt).all())


def _lookup_model(session: Session, model_slug: str) -> ModelCatalog | None:
    return session.scalar(
        select(ModelCatalog).where(
            ModelCatalog.slug == model_slug,
            ModelCatalog.is_active.is_(True),
        )
    )


def _wallet_for_user(session: Session, user_id) -> Wallet:
    wallet = get_wallet_by_user_id(session, user_id)
    if wallet is None:
        wallet = get_or_create_wallet(session, user_id)
    return wallet


def _build_response(
    *,
    model: str,
    content: str,
    input_tokens: int,
    output_tokens: int,
) -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    }


def create_chat_completion(
    session: Session,
    *,
    caller: GatewayCaller,
    request_id: str,
    model: str,
    messages: list[dict],
    max_tokens: int | None = None,
) -> ChatCompletionResult:
    enforce_model_access_for_group(session, caller.access_group_id, model)

    prompt = "\n".join(
        message.get("content", "")
        for message in messages
        if isinstance(message.get("content"), str)
    )
    estimated_tokens = estimate_prompt_tokens(prompt) + (max_tokens or 256)
    check_rate_limits(
        caller.rate_limit_key,
        rpm_limit=caller.rpm_limit,
        tpm_limit=caller.tpm_limit,
        estimated_tokens=estimated_tokens,
    )

    wallet = _wallet_for_user(session, caller.user_id)
    catalog_model = _lookup_model(session, model)
    model_id = catalog_model.id if catalog_model else None
    partner_account_id = caller.partner_account_id

    hold_estimate = estimate_hold_microdollars(
        model,
        max_tokens=max_tokens,
        session=session,
        model_id=model_id,
        partner_account_id=partner_account_id,
    )

    # App-scoped requests enforce the per-app spend cap on the Redis fast path
    # before any balance hold or provider call.
    if caller.is_app_scoped:
        enforce_app_allowance(session, caller.app_install_id, hold_estimate)

    virtual_key = (
        session.get(VirtualKey, caller.virtual_key_id)
        if caller.virtual_key_id is not None
        else None
    )

    check_and_hold(
        session,
        wallet.id,
        request_id,
        hold_estimate,
        virtual_key=virtual_key,
    )

    started = time.perf_counter()
    try:
        routed = route_chat_completion(model, messages)
    except (ProviderError, ValueError) as exc:
        release_hold(session, request_id)
        raise ProviderError(str(exc)) from exc

    pricing: ChargeBreakdown = calculate_charge(
        session,
        base_cost_microdollars=routed.completion.base_cost_microdollars,
        model_id=model_id,
        input_tokens=routed.completion.usage.input_tokens,
        output_tokens=routed.completion.usage.output_tokens,
        partner_account_id=partner_account_id,
    )
    latency_ms = int((time.perf_counter() - started) * 1000)

    settle_metadata = {}
    if caller.is_app_scoped:
        settle_metadata["app_install_id"] = str(caller.app_install_id)

    settle_result = settle_usage(
        session,
        request_id=request_id,
        user_id=caller.user_id,
        wallet_id=wallet.id,
        model=model,
        provider=routed.provider,
        input_tokens=routed.completion.usage.input_tokens,
        output_tokens=routed.completion.usage.output_tokens,
        base_cost_microdollars=pricing.base_cost_microdollars,
        charged_microdollars=pricing.charged_microdollars,
        platform_fee_microdollars=pricing.platform_fee_microdollars,
        partner_margin_microdollars=pricing.partner_margin_microdollars,
        partner_account_id=partner_account_id,
        virtual_key_id=caller.virtual_key_id,
        latency_ms=latency_ms,
        virtual_key=virtual_key,
        metadata=settle_metadata,
    )

    # App-scoped: increment the per-app allowance (authoritative DB write +
    # Redis fast-path projection). Gated by `created` so retries are idempotent.
    if caller.is_app_scoped and settle_result.created:
        install = session.get(AppInstall, caller.app_install_id, with_for_update=True)
        if install is not None and install.revoked_at is None:
            install.allowance_spent_microdollars += pricing.charged_microdollars
            session.flush()
            allowance_cache.increment_allowance_spent(
                caller.app_install_id, pricing.charged_microdollars
            )

    if virtual_key is not None:
        virtual_key.last_used_at = datetime.now(UTC)
    session.flush()

    response_body = _build_response(
        model=model,
        content=routed.completion.content,
        input_tokens=routed.completion.usage.input_tokens,
        output_tokens=routed.completion.usage.output_tokens,
    )
    return ChatCompletionResult(
        response_body=response_body,
        charged_microdollars=pricing.charged_microdollars,
        balance_remaining_microdollars=settle_result.settle_result.debit.wallet.balance_microdollars,
        provider=routed.provider,
    )
