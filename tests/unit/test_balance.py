import pytest

from services.wallet.balance import (
    check_and_hold,
    release_hold,
    settle_hold,
    wallet_summary,
)
from services.wallet.ledger import (
    InsufficientBalanceError,
    SpendLimitExceededError,
    adjust_wallet,
    debit_wallet,
    refund_wallet,
)


def test_refund_wallet(db_session, sandbox_wallet):
    before = sandbox_wallet.balance_microdollars
    result = refund_wallet(
        db_session,
        sandbox_wallet.id,
        500_000,
        idempotency_key="refund-1",
        reference_type="admin",
    )

    assert result.created
    assert result.entry.entry_type == "refund"
    assert sandbox_wallet.balance_microdollars == before + 500_000


def test_adjust_wallet_credit_and_debit(db_session, sandbox_wallet):
    credit = adjust_wallet(
        db_session,
        sandbox_wallet.id,
        100_000,
        idempotency_key="adj-credit",
        direction="credit",
    )
    assert credit.created
    assert credit.entry.entry_type == "adjustment"

    balance_after_credit = sandbox_wallet.balance_microdollars
    debit = adjust_wallet(
        db_session,
        sandbox_wallet.id,
        50_000,
        idempotency_key="adj-debit",
        direction="debit",
    )
    assert debit.created
    assert sandbox_wallet.balance_microdollars == balance_after_credit - 50_000


def test_hold_release_and_settle(db_session, sandbox_wallet):
    before_balance = sandbox_wallet.balance_microdollars

    hold = check_and_hold(
        db_session,
        sandbox_wallet.id,
        request_id="req-hold-1",
        estimated_max_microdollars=1_000_000,
    )
    assert hold.created
    assert sandbox_wallet.held_microdollars == 1_000_000
    summary = wallet_summary(db_session, sandbox_wallet)
    assert summary.available_microdollars == before_balance - 1_000_000

    settled = settle_hold(
        db_session,
        request_id="req-hold-1",
        actual_microdollars=400_000,
    )
    assert settled.debit.created
    assert sandbox_wallet.held_microdollars == 0
    assert sandbox_wallet.balance_microdollars == before_balance - 400_000


def test_hold_idempotency(db_session, sandbox_wallet):
    first = check_and_hold(
        db_session,
        sandbox_wallet.id,
        request_id="req-hold-dup",
        estimated_max_microdollars=200_000,
    )
    second = check_and_hold(
        db_session,
        sandbox_wallet.id,
        request_id="req-hold-dup",
        estimated_max_microdollars=200_000,
    )

    assert first.created
    assert not second.created
    assert first.hold.id == second.hold.id
    assert sandbox_wallet.held_microdollars == 200_000


def test_release_hold(db_session, sandbox_wallet):
    check_and_hold(
        db_session,
        sandbox_wallet.id,
        request_id="req-release",
        estimated_max_microdollars=300_000,
    )
    before = sandbox_wallet.balance_microdollars

    released = release_hold(db_session, "req-release")
    assert released is not None
    assert released.status == "released"
    assert sandbox_wallet.held_microdollars == 0
    assert sandbox_wallet.balance_microdollars == before


def test_settle_hold_idempotency(db_session, sandbox_wallet):
    check_and_hold(
        db_session,
        sandbox_wallet.id,
        request_id="req-settle-dup",
        estimated_max_microdollars=500_000,
    )
    before = sandbox_wallet.balance_microdollars

    first = settle_hold(db_session, "req-settle-dup", actual_microdollars=100_000)
    second = settle_hold(db_session, "req-settle-dup", actual_microdollars=100_000)

    assert first.debit.created
    assert not second.debit.created
    assert sandbox_wallet.balance_microdollars == before - 100_000


def test_wallet_monthly_spend_limit(db_session, sandbox_wallet):
    sandbox_wallet.spend_limit_microdollars = 1_000_000
    sandbox_wallet.balance_microdollars = 5_000_000
    db_session.flush()

    debit_wallet(
        db_session,
        sandbox_wallet.id,
        800_000,
        idempotency_key="spend-1",
    )

    with pytest.raises(SpendLimitExceededError):
        debit_wallet(
            db_session,
            sandbox_wallet.id,
            300_000,
            idempotency_key="spend-2",
        )


def test_virtual_key_budget_limit(db_session, sandbox_wallet, sandbox_key):
    vkey, _ = sandbox_key
    vkey.budget_microdollars = 500_000
    db_session.flush()

    debit_wallet(
        db_session,
        sandbox_wallet.id,
        400_000,
        idempotency_key="key-spend-1",
        virtual_key=vkey,
    )

    with pytest.raises(SpendLimitExceededError):
        debit_wallet(
            db_session,
            sandbox_wallet.id,
            200_000,
            idempotency_key="key-spend-2",
            virtual_key=vkey,
        )


def test_insufficient_balance_on_hold(db_session, sandbox_wallet):
    sandbox_wallet.balance_microdollars = 100_000
    sandbox_wallet.held_microdollars = 0
    db_session.flush()

    with pytest.raises(InsufficientBalanceError):
        check_and_hold(
            db_session,
            sandbox_wallet.id,
            request_id="req-fail",
            estimated_max_microdollars=200_000,
        )
