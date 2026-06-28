from services.gateway.mock_provider import estimate_base_cost
from services.pricing.engine import calculate_charge


def estimate_hold_microdollars(
    model: str,
    *,
    max_tokens: int | None = None,
    session=None,
    model_id=None,
    partner_account_id=None,
) -> int:
    """Pessimistic upper bound for pre-request balance hold."""
    output_tokens = max_tokens if max_tokens is not None else 4096
    input_tokens = 4096
    base = estimate_base_cost(model, input_tokens, output_tokens)
    if session is not None and model_id is not None:
        pricing = calculate_charge(
            session,
            base_cost_microdollars=base,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            partner_account_id=partner_account_id,
        )
        return max(pricing.charged_microdollars, 100_000)
    return max(base, 100_000)
