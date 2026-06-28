from services.wallet.ledger import credit_wallet
from services.wallet.payments import process_stripe_topup_webhook


def test_webhook_idempotency(db_session, sandbox_wallet):
    result1 = process_stripe_topup_webhook(
        db_session,
        wallet_id=sandbox_wallet.id,
        amount_microdollars=2_000_000,
        stripe_event_id="evt_test_123",
        stripe_checkout_session_id="cs_test_123",
    )
    result2 = process_stripe_topup_webhook(
        db_session,
        wallet_id=sandbox_wallet.id,
        amount_microdollars=2_000_000,
        stripe_event_id="evt_test_123",
        stripe_checkout_session_id="cs_test_123",
    )

    assert result1.created
    assert not result2.created
    assert result1.payment_intent.id == result2.payment_intent.id
    assert sandbox_wallet.balance_microdollars == 5_000_000 + 2_000_000


def test_webhook_ledger_credit_is_idempotent(db_session, sandbox_wallet):
    process_stripe_topup_webhook(
        db_session,
        wallet_id=sandbox_wallet.id,
        amount_microdollars=1_000_000,
        stripe_event_id="evt_dup_ledger",
    )

    first_balance = sandbox_wallet.balance_microdollars
    credit_wallet(
        db_session,
        sandbox_wallet.id,
        1_000_000,
        idempotency_key="stripe:evt_dup_ledger",
    )

    assert sandbox_wallet.balance_microdollars == first_balance
