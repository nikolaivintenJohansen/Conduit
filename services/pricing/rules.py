from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.shared.models import ModelCatalog, PartnerAccount, PriceRule


class PartnerNotFoundError(ValueError):
    pass


class ModelNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class CreatePriceRuleInput:
    model_slug: str
    markup_bps: int = 0
    price_per_m_input_microdollars: int | None = None
    price_per_m_output_microdollars: int | None = None
    effective_from: datetime | None = None


def get_partner_by_slug(session: Session, slug: str) -> PartnerAccount | None:
    return session.scalar(
        select(PartnerAccount).where(
            PartnerAccount.slug == slug,
            PartnerAccount.status == "active",
        )
    )


def get_partner_by_id(session: Session, partner_account_id: UUID) -> PartnerAccount | None:
    return session.get(PartnerAccount, partner_account_id)


def get_model_by_slug(session: Session, slug: str) -> ModelCatalog | None:
    return session.scalar(
        select(ModelCatalog).where(
            ModelCatalog.slug == slug,
            ModelCatalog.is_active.is_(True),
        )
    )


def list_price_rules(
    session: Session,
    partner_account_id: UUID,
    *,
    model_slug: str | None = None,
) -> list[PriceRule]:
    stmt = (
        select(PriceRule)
        .where(PriceRule.partner_account_id == partner_account_id)
        .order_by(PriceRule.model_id, PriceRule.effective_from.desc())
    )
    if model_slug is not None:
        model = get_model_by_slug(session, model_slug)
        if model is None:
            return []
        stmt = stmt.where(PriceRule.model_id == model.id)
    return list(session.scalars(stmt).all())


def create_price_rule(
    session: Session,
    partner_account_id: UUID,
    data: CreatePriceRuleInput,
) -> PriceRule:
    partner = get_partner_by_id(session, partner_account_id)
    if partner is None or partner.status != "active":
        raise PartnerNotFoundError("partner not found")

    model = get_model_by_slug(session, data.model_slug)
    if model is None:
        raise ModelNotFoundError(f"model not found: {data.model_slug}")

    if data.markup_bps < 0:
        raise ValueError("markup_bps must be non-negative")
    if data.price_per_m_input_microdollars is not None and data.price_per_m_input_microdollars < 0:
        raise ValueError("price_per_m_input_microdollars must be non-negative")
    if (
        data.price_per_m_output_microdollars is not None
        and data.price_per_m_output_microdollars < 0
    ):
        raise ValueError("price_per_m_output_microdollars must be non-negative")

    rule = PriceRule(
        partner_account_id=partner_account_id,
        model_id=model.id,
        markup_bps=data.markup_bps,
        price_per_m_input_microdollars=data.price_per_m_input_microdollars,
        price_per_m_output_microdollars=data.price_per_m_output_microdollars,
        effective_from=data.effective_from or datetime.now(UTC),
    )
    session.add(rule)
    session.flush()
    return rule
