"""Partner-admin settlement endpoints (Phase 7).

Manual trigger for batch settlement (back-fill or external cron) plus an audit
listing of past settlement batches. The nightly run is driven by
``services/wallet/settlement_scheduler.py``; these routes cover the operational
surface.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from services.pricing.deps import require_partner_admin
from services.pricing.rules import get_partner_by_slug
from services.shared.config import get_settings
from services.shared.models import SettlementBatch
from services.wallet.deps import get_db
from services.wallet import settlement as settlement_service

router = APIRouter(prefix="/wallet/v1/partner", tags=["Partner Settlement"])


class PartnerSettlementStatus(BaseModel):
    partner_account_id: UUID
    partner_slug: str
    status: str
    event_count: int
    payout_microdollars: int
    error: str | None


class SettlementRunResponse(BaseModel):
    started_at: datetime
    finished_at: datetime
    cleared: int
    failed: int
    skipped: int
    results: list[PartnerSettlementStatus]


class SettlementBatchResponse(BaseModel):
    id: UUID
    partner_account_id: UUID
    period_start: datetime
    period_end: datetime
    gross_usage_microdollars: int
    platform_fee_microdollars: int
    partner_payout_microdollars: int
    provider_cost_microdollars: int
    partner_margin_microdollars: int
    event_count: int
    status: str
    stripe_transfer_id: str | None
    error_message: str | None
    created_at: datetime
    cleared_at: datetime | None


class SettlementBatchListResponse(BaseModel):
    data: list[SettlementBatchResponse]


def _batch_response(batch: SettlementBatch) -> SettlementBatchResponse:
    return SettlementBatchResponse(
        id=batch.id,
        partner_account_id=batch.partner_account_id,
        period_start=batch.period_start,
        period_end=batch.period_end,
        gross_usage_microdollars=batch.gross_usage_microdollars,
        platform_fee_microdollars=batch.platform_fee_microdollars,
        partner_payout_microdollars=batch.partner_payout_microdollars,
        provider_cost_microdollars=batch.provider_cost_microdollars,
        partner_margin_microdollars=batch.partner_margin_microdollars,
        event_count=batch.event_count,
        status=batch.status,
        stripe_transfer_id=batch.stripe_transfer_id,
        error_message=batch.error_message,
        created_at=batch.created_at,
        cleared_at=batch.cleared_at,
    )


@router.post(
    "/settlement/run",
    response_model=SettlementRunResponse,
    status_code=status.HTTP_200_OK,
)
def run_settlement(
    partner_slug: str | None = Query(default=None, description="Limit the run to one partner"),
    db: Session = Depends(get_db),
    _: None = Depends(require_partner_admin),
) -> SettlementRunResponse:
    if partner_slug is not None:
        partner = get_partner_by_slug(db, partner_slug)
        if partner is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "partner_not_found", "message": "Partner not found"}},
            )
    report = settlement_service.run_settlement_once(
        session=db, partner_slug=partner_slug
    )
    return SettlementRunResponse(
        started_at=report.started_at,
        finished_at=report.finished_at,
        cleared=len(report.cleared),
        failed=len(report.failed),
        skipped=len(report.results) - len(report.cleared) - len(report.failed),
        results=[
            PartnerSettlementStatus(
                partner_account_id=r.partner_account_id,
                partner_slug=r.partner_slug,
                status=r.status,
                event_count=r.event_count,
                payout_microdollars=r.payout_microdollars,
                error=r.error,
            )
            for r in report.results
        ],
    )


@router.get(
    "/{partner_slug}/settlement/batches",
    response_model=SettlementBatchListResponse,
)
def list_batches(
    partner_slug: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: None = Depends(require_partner_admin),
) -> SettlementBatchListResponse:
    partner = get_partner_by_slug(db, partner_slug)
    if partner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "partner_not_found", "message": "Partner not found"}},
        )
    batches = settlement_service.list_settlement_batches(db, partner.id, limit=limit)
    return SettlementBatchListResponse(data=[_batch_response(b) for b in batches])


def get_settlement_settings() -> dict:
    settings = get_settings()
    return {
        "settlement_enabled": settings.settlement_enabled,
        "settlement_cron": settings.settlement_cron,
        "settlement_min_payout_microdollars": settings.settlement_min_payout_microdollars,
    }
