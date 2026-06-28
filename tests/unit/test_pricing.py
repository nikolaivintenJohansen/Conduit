from datetime import UTC, datetime, timedelta

from services.pricing.engine import calculate_charge, resolve_price_rule


def test_mvp_pass_through_pricing(db_session, model_catalog):
    breakdown = calculate_charge(
        db_session,
        base_cost_microdollars=7500,
        model_id=model_catalog.id,
        input_tokens=1000,
        output_tokens=500,
    )

    assert breakdown.base_cost_microdollars == 7500
    assert breakdown.partner_margin_microdollars == 0
    assert breakdown.platform_fee_microdollars == 0
    assert breakdown.charged_microdollars == 7500


def test_partner_list_price_markup(db_session, model_catalog, partner_with_pricing):
    breakdown = calculate_charge(
        db_session,
        base_cost_microdollars=7500,
        model_id=model_catalog.id,
        input_tokens=1_000_000,
        output_tokens=500_000,
        partner_account_id=partner_with_pricing.id,
    )

    # List price: $0.20/M input + $0.40/M output on 1M/500k tokens = $0.60
    assert breakdown.partner_margin_microdollars == 600_000 - 7500
    assert breakdown.platform_fee_microdollars > 0
    assert (
        breakdown.charged_microdollars
        == breakdown.base_cost_microdollars
        + breakdown.partner_margin_microdollars
        + breakdown.platform_fee_microdollars
    )


def test_partner_markup_bps(db_session, model_catalog, partner_with_pricing):
    from services.shared.models import PriceRule

    partner_with_pricing.default_platform_fee_bps = 0
    for rule in db_session.query(PriceRule).filter_by(partner_account_id=partner_with_pricing.id):
        rule.price_per_m_input_microdollars = None
        rule.price_per_m_output_microdollars = None
        rule.markup_bps = 2000
    db_session.flush()

    breakdown = calculate_charge(
        db_session,
        base_cost_microdollars=10_000,
        model_id=model_catalog.id,
        input_tokens=1000,
        output_tokens=500,
        partner_account_id=partner_with_pricing.id,
    )

    assert breakdown.partner_margin_microdollars == 2000
    assert breakdown.charged_microdollars == 12_000


def test_effective_date_rule_resolution(db_session, model_catalog, partner_with_pricing):
    from services.shared.models import PriceRule

    old_rule = PriceRule(
        partner_account_id=partner_with_pricing.id,
        model_id=model_catalog.id,
        markup_bps=5000,
        effective_from=datetime.now(UTC) - timedelta(days=30),
        effective_to=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(old_rule)
    db_session.flush()

    at_old = datetime.now(UTC) - timedelta(days=15)
    resolved_old = resolve_price_rule(
        db_session,
        partner_with_pricing.id,
        model_catalog.id,
        at_time=at_old,
    )
    assert resolved_old is not None
    assert resolved_old.markup_bps == 5000

    resolved_now = resolve_price_rule(
        db_session,
        partner_with_pricing.id,
        model_catalog.id,
    )
    assert resolved_now is not None
    assert resolved_now.markup_bps == 1000
