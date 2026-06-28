from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from services.shared.models import User
from services.wallet.deps import get_current_user, get_db
from services.wallet.usage import list_usage_events

router = APIRouter(prefix="/wallet/v1", tags=["Usage"])


class UsageEventResponse(BaseModel):
    id: UUID
    request_id: str
    model: str
    input_tokens: int
    output_tokens: int
    charged_microdollars: int
    created_at: datetime


class UsageListResponse(BaseModel):
    data: list[UsageEventResponse]
    next_cursor: str | None = None


@router.get("/usage", response_model=UsageListResponse)
def get_usage(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> UsageListResponse:
    page = list_usage_events(db, user.id, limit=limit, cursor=cursor)
    return UsageListResponse(
        data=[
            UsageEventResponse(
                id=event.id,
                request_id=event.request_id,
                model=event.model,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                charged_microdollars=event.charged_microdollars,
                created_at=event.created_at,
            )
            for event in page.events
        ],
        next_cursor=page.next_cursor,
    )
