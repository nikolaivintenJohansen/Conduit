from services.gateway.mock_provider import mock_chat_completion
from services.pricing.engine import calculate_charge
from services.wallet.balance import check_and_hold
from services.wallet.ledger import has_sufficient_balance
from services.wallet.usage import settle_usage


def test_mock_provider_returns_usage_and_cost():
    result = mock_chat_completion("gpt-4o-mini", "hello sandbox world")

    assert result.model == "gpt-4o-mini"
    assert result.usage.input_tokens > 0
    assert result.usage.output_tokens > 0
    assert result.base_cost_microdollars > 0
    assert "hello sandbox world" in result.content


def test_sandbox_routing_and_billing_flow(
    db_session, sandbox_wallet, sandbox_user, sandbox_key, model_catalog
):
    vkey, _ = sandbox_key
    completion = mock_chat_completion("gpt-4o-mini", "bill this request")
    pricing = calculate_charge(
        db_session,
        base_cost_microdollars=completion.base_cost_microdollars,
        model_id=model_catalog.id,
        input_tokens=completion.usage.input_tokens,
        output_tokens=completion.usage.output_tokens,
    )

    assert has_sufficient_balance(sandbox_wallet, pricing.charged_microdollars)

    request_id = "req-mock-001"
    check_and_hold(
        db_session,
        sandbox_wallet.id,
        request_id,
        estimated_max_microdollars=pricing.charged_microdollars,
        virtual_key=vkey,
    )

    before = sandbox_wallet.balance_microdollars
    result = settle_usage(
        db_session,
        request_id=request_id,
        user_id=sandbox_user.id,
        wallet_id=sandbox_wallet.id,
        model="gpt-4o-mini",
        provider="mock",
        input_tokens=completion.usage.input_tokens,
        output_tokens=completion.usage.output_tokens,
        base_cost_microdollars=pricing.base_cost_microdollars,
        charged_microdollars=pricing.charged_microdollars,
        virtual_key_id=vkey.id,
        virtual_key=vkey,
    )

    assert result.created
    assert sandbox_wallet.balance_microdollars == before - pricing.charged_microdollars
    assert result.settle_result.debit.entry.reference_id == result.usage_event.id
