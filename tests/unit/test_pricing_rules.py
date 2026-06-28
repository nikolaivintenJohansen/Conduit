from datetime import UTC, datetime, timedelta

from services.pricing.rules import CreatePriceRuleInput, create_price_rule, list_price_rules


def test_create_and_list_price_rules(db_session, model_catalog, partner_with_pricing):
    rule = create_price_rule(
        db_session,
        partner_with_pricing.id,
        CreatePriceRuleInput(
            model_slug=model_catalog.slug,
            markup_bps=1500,
            price_per_m_input_microdollars=250_000,
            price_per_m_output_microdollars=900_000,
            effective_from=datetime.now(UTC) + timedelta(days=1),
        ),
    )

    assert rule.markup_bps == 1500
    assert rule.model_id == model_catalog.id

    all_rules = list_price_rules(db_session, partner_with_pricing.id)
    assert len(all_rules) >= 2

    filtered = list_price_rules(db_session, partner_with_pricing.id, model_slug=model_catalog.slug)
    assert all(r.model_id == model_catalog.id for r in filtered)
