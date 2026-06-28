import pytest

from services.wallet.ledger import (
    InsufficientBalanceError,
    credit_wallet,
    debit_wallet,
    has_sufficient_balance,
)


def test_credit_and_debit_wallet(db_session, sandbox_wallet):
    credit = credit_wallet(
        db_session,
        sandbox_wallet.id,
        1_000_000,
        idempotency_key="credit-1",
    )
    assert credit.created
    assert credit.wallet.balance_microdollars == 6_000_000

    debit = debit_wallet(
        db_session,
        sandbox_wallet.id,
        500_000,
        idempotency_key="debit-1",
    )
    assert debit.created
    assert debit.wallet.balance_microdollars == 5_500_000


def test_debit_idempotency(db_session, sandbox_wallet):
    starting_balance = sandbox_wallet.balance_microdollars
    first = debit_wallet(
        db_session,
        sandbox_wallet.id,
        100_000,
        idempotency_key="same-key",
    )
    second = debit_wallet(
        db_session,
        sandbox_wallet.id,
        100_000,
        idempotency_key="same-key",
    )

    assert first.created
    assert not second.created
    assert first.entry.id == second.entry.id
    assert second.wallet.balance_microdollars == starting_balance - 100_000


def test_credit_idempotency(db_session, sandbox_wallet):
    first = credit_wallet(
        db_session,
        sandbox_wallet.id,
        250_000,
        idempotency_key="credit-same",
    )
    second = credit_wallet(
        db_session,
        sandbox_wallet.id,
        250_000,
        idempotency_key="credit-same",
    )

    assert first.created
    assert not second.created
    assert first.entry.id == second.entry.id


def test_insufficient_balance_blocks_debit(db_session, sandbox_wallet):
    sandbox_wallet.balance_microdollars = 100_000
    db_session.flush()

    assert not has_sufficient_balance(sandbox_wallet, 200_000)

    with pytest.raises(InsufficientBalanceError):
        debit_wallet(
            db_session,
            sandbox_wallet.id,
            200_000,
            idempotency_key="fail-debit",
        )
