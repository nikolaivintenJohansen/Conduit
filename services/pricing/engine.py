from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.shared.models import PartnerAccount, PriceRule


@dataclass(frozen=True)
class ChargeBreakdown:
    base_cost_microdollars: int
    partner_margin_microdollars: int
    platform_fee_microdollars: int
    charged_microdollars: int


def resolve_price_rule(
    session: Session,
    partner_account_id,
    model_id,
    at_time: datetime | None = None,
) -> PriceRule | None:
    now = at_time or datetime.now(UTC)
    stmt = (
        select(PriceRule)
        .where(
            PriceRule.partner_account_id == partner_account_id,
            PriceRule.model_id == model_id,
            PriceRule.effective_from <= now,
        )
        .where((PriceRule.effective_to.is_(None)) | (PriceRule.effective_to > now))
        .order_by(PriceRule.effective_from.desc())
        .limit(1)
    )
    return session.scalar(stmt)


def calculate_charge(
    session: Session,
    *,
    base_cost_microdollars: int,
    model_id,
    input_tokens: int,
    output_tokens: int,
    partner_account_id=None,
    at_time: datetime | None = None,
) -> ChargeBreakdown:
    partner_margin = 0
    platform_fee_bps = 0

    if partner_account_id is not None:
        partner = session.get(PartnerAccount, partner_account_id)
        if partner:
            platform_fee_bps = partner.default_platform_fee_bps
        rule = resolve_price_rule(session, partner_account_id, model_id, at_time=at_time)
        if rule:
            if rule.price_per_m_input_microdollars is not None:
                input_cost = (input_tokens * rule.price_per_m_input_microdollars) // 1_000_000
                output_cost = (
                    output_tokens * (rule.price_per_m_output_microdollars or 0)
                ) // 1_000_000
                list_price = input_cost + output_cost
                partner_margin = max(0, list_price - base_cost_microdollars)
            else:
                partner_margin = (base_cost_microdollars * rule.markup_bps) // 10_000

    subtotal = base_cost_microdollars + partner_margin
    platform_fee = (subtotal * platform_fee_bps) // 10_000
    charged = subtotal + platform_fee

    return ChargeBreakdown(
        base_cost_microdollars=base_cost_microdollars,
        partner_margin_microdollars=partner_margin,
        platform_fee_microdollars=platform_fee,
        charged_microdollars=charged,
    )
