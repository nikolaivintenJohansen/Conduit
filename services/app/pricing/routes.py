from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from services.pricing.deps import require_partner_admin
from services.pricing.rules import (
    CreatePriceRuleInput,
    ModelNotFoundError,
    create_price_rule,
    get_partner_by_slug,
    list_price_rules,
)
from services.wallet.deps import get_db

router = APIRouter(prefix="/wallet/v1/partner", tags=["Partner Pricing"])


class PartnerAccountResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    status: str
    default_platform_fee_bps: int


class PriceRuleResponse(BaseModel):
    id: UUID
    model_slug: str
    markup_bps: int
    price_per_m_input_microdollars: int | None
    price_per_m_output_microdollars: int | None
    effective_from: datetime
    effective_to: datetime | None


class PriceRuleListResponse(BaseModel):
    data: list[PriceRuleResponse]


class CreatePriceRuleRequest(BaseModel):
    model_slug: str = Field(min_length=1)
    markup_bps: int = Field(default=0, ge=0)
    price_per_m_input_microdollars: int | None = Field(default=None, ge=0)
    price_per_m_output_microdollars: int | None = Field(default=None, ge=0)
    effective_from: datetime | None = None


def _rule_response(session, rule) -> PriceRuleResponse:
    from services.shared.models import ModelCatalog

    catalog_model = session.get(ModelCatalog, rule.model_id)
    model_slug = catalog_model.slug if catalog_model else "unknown"
    return PriceRuleResponse(
        id=rule.id,
        model_slug=model_slug,
        markup_bps=rule.markup_bps,
        price_per_m_input_microdollars=rule.price_per_m_input_microdollars,
        price_per_m_output_microdollars=rule.price_per_m_output_microdollars,
        effective_from=rule.effective_from,
        effective_to=rule.effective_to,
    )


@router.get("/{partner_slug}", response_model=PartnerAccountResponse)
def get_partner(
    partner_slug: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_partner_admin),
) -> PartnerAccountResponse:
    partner = get_partner_by_slug(db, partner_slug)
    if partner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "partner_not_found", "message": "Partner not found"}},
        )
    return PartnerAccountResponse(
        id=partner.id,
        name=partner.name,
        slug=partner.slug,
        status=partner.status,
        default_platform_fee_bps=partner.default_platform_fee_bps,
    )


@router.get("/{partner_slug}/price-rules", response_model=PriceRuleListResponse)
def get_price_rules(
    partner_slug: str,
    db: Session = Depends(get_db),
    model_slug: str | None = Query(default=None),
    _: None = Depends(require_partner_admin),
) -> PriceRuleListResponse:
    partner = get_partner_by_slug(db, partner_slug)
    if partner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "partner_not_found", "message": "Partner not found"}},
        )

    rules = list_price_rules(db, partner.id, model_slug=model_slug)
    return PriceRuleListResponse(data=[_rule_response(db, rule) for rule in rules])


@router.post("/{partner_slug}/price-rules", response_model=PriceRuleResponse, status_code=201)
def post_price_rule(
    partner_slug: str,
    body: CreatePriceRuleRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_partner_admin),
) -> PriceRuleResponse:
    partner = get_partner_by_slug(db, partner_slug)
    if partner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "partner_not_found", "message": "Partner not found"}},
        )

    try:
        rule = create_price_rule(
            db,
            partner.id,
            CreatePriceRuleInput(
                model_slug=body.model_slug,
                markup_bps=body.markup_bps,
                price_per_m_input_microdollars=body.price_per_m_input_microdollars,
                price_per_m_output_microdollars=body.price_per_m_output_microdollars,
                effective_from=body.effective_from,
            ),
        )
    except ModelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "model_not_found", "message": str(exc)}},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_price_rule", "message": str(exc)}},
        ) from exc

    return _rule_response(db, rule)
