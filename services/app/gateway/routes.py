from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from services.gateway.access import AccessDeniedError, AllowanceExceededError, AppRevokedError
from services.gateway.deps import GatewayCaller, get_gateway_caller
from services.gateway.rate_limit import RateLimitExceededError
from services.gateway.router import ProviderError
from services.gateway.service import create_chat_completion, list_allowed_models
from services.wallet.deps import get_db
from services.wallet.ledger import InsufficientBalanceError, SpendLimitExceededError

router = APIRouter(prefix="/v1", tags=["Gateway"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None


class ModelListResponse(BaseModel):
    object: str = "list"
    data: list[dict]


def _error_detail(code: str, message: str, request_id: str) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id}}


def _request_id(request: Request, header_value: str | None) -> str:
    if header_value:
        return header_value
    return getattr(request.state, "request_id", "unknown")


@router.post("/chat/completions")
def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
    caller: GatewayCaller = Depends(get_gateway_caller),
    db: Session = Depends(get_db),
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
):
    request_id = _request_id(request, x_request_id)

    if body.stream:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error_detail(
                "unsupported_request",
                "Streaming is not supported in MVP",
                request_id,
            ),
        )

    try:
        result = create_chat_completion(
            db,
            caller=caller,
            request_id=request_id,
            model=body.model,
            messages=[message.model_dump() for message in body.messages],
            max_tokens=body.max_tokens,
        )
    except AccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_error_detail("model_not_allowed", str(exc), request_id),
        ) from exc
    except InsufficientBalanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=_error_detail("insufficient_balance", str(exc), request_id),
        ) from exc
    except SpendLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=_error_detail("insufficient_balance", str(exc), request_id),
        ) from exc
    except AllowanceExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=_error_detail("allowance_exceeded", str(exc), request_id),
        ) from exc
    except AppRevokedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_error_detail("app_revoked", str(exc), request_id),
        ) from exc
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_error_detail("rate_limit_exceeded", str(exc), request_id),
        ) from exc
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_error_detail("provider_error", str(exc), request_id),
        ) from exc

    request.state.gateway_cost_microdollars = result.charged_microdollars
    request.state.gateway_balance_microdollars = result.balance_remaining_microdollars
    return result.response_body


@router.get("/models", response_model=ModelListResponse)
def list_models(
    caller: GatewayCaller = Depends(get_gateway_caller),
    db: Session = Depends(get_db),
) -> ModelListResponse:
    models = list_allowed_models(db, caller.access_group_id)
    return ModelListResponse(
        data=[
            {
                "id": model.slug,
                "object": "model",
                "owned_by": model.provider,
            }
            for model in models
        ]
    )
