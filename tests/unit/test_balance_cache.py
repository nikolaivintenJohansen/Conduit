"""Unit tests for the Redis balance cache (in-memory fallback path)."""

from __future__ import annotations

import pytest

from services.gateway import balance_cache


def _set(wallet_id, balance, held=0, spend_limit=None, monthly_spent=0, spend_period=None):
    balance_cache.set_balance_state(
        wallet_id,
        balance_microdollars=balance,
        held_microdollars=held,
        spend_limit_microdollars=spend_limit,
        monthly_spent_microdollars=monthly_spent,
        spend_period=spend_period,
    )


@pytest.fixture(autouse=True)
def _reset():
    balance_cache.reset_balance_cache()
    yield
    balance_cache.reset_balance_cache()


def test_set_and_get_balance_state():
    _set("wallet-1", 5_000_000)
    state = balance_cache.get_balance_state("wallet-1")
    assert state["balance_microdollars"] == 5_000_000
    assert state["held_microdollars"] == 0
    assert state["spend_limit_microdollars"] is None
    assert state["monthly_spent_microdollars"] == 0
    assert state["spend_period"] is not None  # defaults to current YYYY-MM
    assert state["as_of_ms"] >= 0


def test_place_hold_succeeds_and_increments_held():
    _set("wallet-1", 5_000_000)
    ok, held, available = balance_cache.place_hold("wallet-1", "req-1", 1_000_000)
    assert ok is True
    assert held == 1_000_000
    assert available == 4_000_000

    hold = balance_cache.get_hold("req-1")
    assert hold is not None
    assert int(hold["estimated_max_microdollars"]) == 1_000_000


def test_place_hold_rejects_when_insufficient():
    _set("wallet-1", 1_000_000)
    ok, held, available = balance_cache.place_hold("wallet-1", "req-1", 2_000_000)
    assert ok is False
    assert held == 0
    assert available == 1_000_000
    assert balance_cache.get_hold("req-1") is None


def test_release_hold_debits_balance_and_clears_hold():
    _set("wallet-1", 5_000_000)
    balance_cache.place_hold("wallet-1", "req-1", 1_000_000)
    balance_cache.release_hold("wallet-1", "req-1", 1_000_000, 750_000)

    state = balance_cache.get_balance_state("wallet-1")
    assert state["held_microdollars"] == 0
    assert state["balance_microdollars"] == 4_250_000
    assert balance_cache.get_hold("req-1") is None


def test_cancel_hold_releases_without_debit():
    _set("wallet-1", 5_000_000)
    balance_cache.place_hold("wallet-1", "req-1", 1_000_000)
    balance_cache.cancel_hold("wallet-1", "req-1", 1_000_000)

    state = balance_cache.get_balance_state("wallet-1")
    assert state["held_microdollars"] == 0
    assert state["balance_microdollars"] == 5_000_000


def test_apply_credit_bumps_balance():
    _set("wallet-1", 5_000_000)
    balance_cache.apply_credit("wallet-1", 2_000_000)
    assert balance_cache.get_balance_state("wallet-1")["balance_microdollars"] == 7_000_000


def test_place_hold_is_atomic_under_concurrent_estimates():
    """Two holds that individually fit but together exceed balance: second fails."""
    _set("wallet-1", 3_000_000)
    ok1, _, _ = balance_cache.place_hold("wallet-1", "req-1", 2_000_000)
    ok2, _, available2 = balance_cache.place_hold("wallet-1", "req-2", 2_000_000)
    assert ok1 is True
    assert ok2 is False
    assert available2 == 1_000_000  # 3M balance - 2M held


def test_place_hold_rejects_when_monthly_spend_limit_exceeded():
    """Sufficient balance but monthly_spent + estimate > spend_limit → rejected."""
    _set("wallet-1", 5_000_000, spend_limit=300_000, monthly_spent=250_000)
    ok, held, available, code = balance_cache.place_hold_checked(
        "wallet-1", "req-limit-1", 100_000
    )
    assert ok is False
    assert code == "spend_limit_exceeded"
    assert held == 0  # nothing reserved
    assert balance_cache.get_hold("req-limit-1") is None


def test_place_hold_checked_returns_insufficient_code_when_balance_low():
    _set("wallet-1", 100_000, spend_limit=10_000_000)
    ok, held, available, code = balance_cache.place_hold_checked(
        "wallet-1", "req-low-1", 200_000
    )
    assert ok is False
    assert code == "insufficient_balance"


def test_place_hold_succeeds_when_within_spend_limit():
    _set("wallet-1", 5_000_000, spend_limit=1_000_000, monthly_spent=250_000)
    ok, held, available, code = balance_cache.place_hold_checked(
        "wallet-1", "req-ok-1", 100_000
    )
    assert ok is True
    assert code == "ok"
    assert held == 100_000


def test_incr_monthly_spent_accumulates_within_period():
    _set("wallet-1", 5_000_000, spend_limit=1_000_000, monthly_spent=100_000)
    balance_cache.incr_monthly_spent("wallet-1", 50_000)
    balance_cache.incr_monthly_spent("wallet-1", 25_000)
    state = balance_cache.get_balance_state("wallet-1")
    assert state["monthly_spent_microdollars"] == 175_000


def test_incr_monthly_spent_resets_on_period_rollover():
    _set(
        "wallet-1",
        5_000_000,
        spend_limit=1_000_000,
        monthly_spent=900_000,
        spend_period="1999-01",  # stale period
    )
    balance_cache.incr_monthly_spent("wallet-1", 40_000)
    state = balance_cache.get_balance_state("wallet-1")
    # Rolled over: monthly_spent resets to just this charge, period is current.
    assert state["monthly_spent_microdollars"] == 40_000
    assert state["spend_period"] != "1999-01"
