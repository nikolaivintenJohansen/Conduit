"""Phase 4 fast-path endpoints: POST /v1/authorize and POST /v1/usage (ingestion)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from services.gateway.access import AllowanceExceededError, AppRevokedError
from services.gateway.authorize import authorize_request
from services.gateway.deps import GatewayCaller, get_gateway_caller
from services.gateway.usage_queue import enqueue_event, mark_seen
from services.shared.config import get_settings
from services.wallet.deps import get_db
from services.wallet.ledger import InsufficientBalanceError, SpendLimitExceededError

router = APIRouter(prefix="/v1", tags=["Gateway"])


class AuthorizeRequest(BaseModel):
    model: str
    max_tokens: int | None = None
    requested_reserve_microdollars: int | None = Field(
        default=None, description="Optional explicit reserve (microdollars) instead of an estimate"
    )


class AuthorizeResponse(BaseModel):
    authorized: bool
    request_id: str
    mode: str
    held_microdollars: int
    available_microdollars: int
    balance_microdollars: int
    expires_at_ms: int | None = None


class UsageEventInput(BaseModel):
    request_id: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    provider: str | None = None


class UsageIngestRequest(BaseModel):
    events: list[UsageEventInput]


class UsageIngestResponse(BaseModel):
    accepted: int
    duplicated: int
    stream: str
    request_ids: list[str]


def _request_id(request: Request, header_value: str | None) -> str:
    if header_value:
        return header_value
    return f"req-{uuid.uuid4().hex[:24]}"


@router.post("/authorize", response_model=AuthorizeResponse)
def authorize(
    body: AuthorizeRequest,
    request: Request,
    caller: GatewayCaller = Depends(get_gateway_caller),
    db: Session = Depends(get_db),
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
):
    request_id = _request_id(request, x_request_id)
    try:
        result = authorize_request(
            db,
            caller=caller,
            request_id=request_id,
            model=body.model,
            max_tokens=body.max_tokens,
            requested_reserve_microdollars=body.requested_reserve_microdollars,
        )
    except AllowanceExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=_error("allowance_exceeded", str(exc), request_id),
        ) from exc
    except AppRevokedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_error("app_revoked", str(exc), request_id),
        ) from exc
    except InsufficientBalanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=_error("insufficient_balance", str(exc), request_id),
        ) from exc
    except SpendLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=_error("spend_limit_exceeded", str(exc), request_id),
        ) from exc

    request.state.gateway_cost_microdollars = result.held_microdollars
    request.state.gateway_balance_microdollars = result.balance_microdollars
    return AuthorizeResponse(
        authorized=result.authorized,
        request_id=result.request_id,
        mode=result.mode,
        held_microdollars=result.held_microdollars,
        available_microdollars=result.available_microdollars,
        balance_microdollars=result.balance_microdollars,
        expires_at_ms=result.expires_at_ms,
    )


@router.post("/usage", response_model=UsageIngestResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest_usage(
    body: UsageIngestRequest,
    request: Request,
    caller: GatewayCaller = Depends(get_gateway_caller),
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
):
    if not body.events:
        rid = _request_id(request, x_request_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error("invalid_request", "events list is empty", rid),
        )

    accepted = 0
    duplicated = 0
    request_ids: list[str] = []
    partner_account_id = str(caller.partner_account_id) if caller.partner_account_id else ""
    virtual_key_id = str(caller.virtual_key_id) if caller.virtual_key_id else ""
    app_install_id = str(caller.app_install_id) if caller.is_app_scoped else ""

    for event in body.events:
        if not mark_seen(event.request_id):
            duplicated += 1
            continue
        payload = {
            "request_id": event.request_id,
            "user_id": str(caller.user_id),
            "virtual_key_id": virtual_key_id,
            "app_install_id": app_install_id,
            "partner_account_id": partner_account_id,
            "model": event.model,
            "provider": event.provider or "",
            "input_tokens": event.input_tokens,
            "output_tokens": event.output_tokens,
        }
        # Attach the hold estimate + wallet id so the worker can release the
        # exact reserved amount and debit the right wallet.
        from services.gateway import balance_cache

        hold = balance_cache.get_hold(event.request_id)
        if hold is not None:
            payload["wallet_id"] = hold.get("wallet_id", "")
            try:
                estimate = hold.get("estimated_max_microdollars", 0)
                payload["estimated_max_microdollars"] = int(estimate)
            except (TypeError, ValueError):
                payload["estimated_max_microdollars"] = 0
        enqueue_event(payload)
        accepted += 1
        request_ids.append(event.request_id)

    return UsageIngestResponse(
        accepted=accepted,
        duplicated=duplicated,
        stream=get_settings().usage_stream_name,
        request_ids=request_ids,
    )


def _error(code: str, message: str, request_id: str) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id}}
