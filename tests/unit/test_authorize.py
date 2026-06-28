"""Unit tests for the fast-path authorize logic (Redis hold, in-memory fallback)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from services.gateway import balance_cache
from services.gateway.authorize import authorize_request
from services.gateway.deps import GatewayCaller
from services.wallet.apps import connect_app
from services.wallet.ledger import InsufficientBalanceError, SpendLimitExceededError


@pytest.fixture(autouse=True)
def _reset_caches():
    from services.gateway.allowance_cache import reset_allowance_cache
    from services.gateway.rate_limit import reset_rate_limit_state

    balance_cache.reset_balance_cache()
    reset_allowance_cache()
    reset_rate_limit_state()
    yield
    balance_cache.reset_balance_cache()
    reset_allowance_cache()
    reset_rate_limit_state()


def _caller(user_id, *, app_install_id=None, partner_account_id=None) -> GatewayCaller:
    return GatewayCaller(
        user_id=user_id,
        virtual_key_id=None,
        access_group_id=None,
        partner_account_id=partner_account_id,
        rpm_limit=60,
        tpm_limit=100_000,
        budget_microdollars=None,
        app_install_id=app_install_id,
        scopes=[],
    )


def test_authorize_places_fast_hold(db_session, sandbox_user, sandbox_wallet, model_catalog):
    request_id = f"req-{uuid4().hex[:12]}"
    result = authorize_request(
        db_session,
        caller=_caller(sandbox_user.id),
        request_id=request_id,
        model="gpt-4o-mini",
    )
    assert result.authorized is True
    assert result.mode == "fast"
    assert result.held_microdollars >= 100_000
    assert result.available_microdollars == 5_000_000 - result.held_microdollars

    hold = balance_cache.get_hold(request_id)
    assert hold is not None
    assert int(hold["estimated_max_microdollars"]) == result.held_microdollars


def test_authorize_rejects_insufficient_balance(db_session, sandbox_user, model_catalog):
    # Wallet with barely any balance.
    from services.shared.models import Wallet

    wallet = Wallet(user_id=sandbox_user.id, balance_microdollars=50_000)  # $0.05
    db_session.add(wallet)
    db_session.flush()

    with pytest.raises(InsufficientBalanceError):
        authorize_request(
            db_session,
            caller=_caller(sandbox_user.id),
            request_id=f"req-{uuid4().hex[:12]}",
            model="gpt-4o",
        )


def test_authorize_app_scoped_enforces_allowance(
    db_session, sandbox_user, sandbox_wallet, app_registration, model_catalog
):
    install = connect_app(
        db_session,
        user_id=sandbox_user.id,
        client_id=app_registration.client_id,
        spend_limit_microdollars=50_000,  # $0.05 — below the $0.10 minimum hold
    )
    with pytest.raises(Exception) as exc_info:  # noqa: PT011
        authorize_request(
            db_session,
            caller=_caller(sandbox_user.id, app_install_id=install.id),
            request_id=f"req-{uuid4().hex[:12]}",
            model="gpt-4o-mini",
        )
    from services.gateway.access import AllowanceExceededError

    assert isinstance(exc_info.value, AllowanceExceededError)


def test_authorize_with_explicit_reserve(
    db_session, sandbox_user, sandbox_wallet, model_catalog
):
    request_id = f"req-{uuid4().hex[:12]}"
    result = authorize_request(
        db_session,
        caller=_caller(sandbox_user.id),
        request_id=request_id,
        model="gpt-4o-mini",
        requested_reserve_microdollars=250_000,  # $0.25
    )
    assert result.held_microdollars == 250_000


def test_authorize_rejects_when_monthly_spend_limit_exceeded(
    db_session, sandbox_user, model_catalog
):
    """Fast path rejects when monthly_spent + estimate exceeds spend_limit (Phase 5 hardening)."""
    from services.shared.models import Wallet

    # Balance is plenty, but the monthly cap is below the $0.10 minimum hold.
    wallet = Wallet(
        user_id=sandbox_user.id,
        balance_microdollars=5_000_000,
        spend_limit_microdollars=50_000,  # $0.05
    )
    db_session.add(wallet)
    db_session.flush()

    with pytest.raises(SpendLimitExceededError):
        authorize_request(
            db_session,
            caller=_caller(sandbox_user.id),
            request_id=f"req-{uuid4().hex[:12]}",
            model="gpt-4o-mini",
        )

    # No hold placed.
    assert balance_cache.get_hold("req-limit") is None
    state = balance_cache.get_balance_state(wallet.id)
    assert state is not None
    assert state["held_microdollars"] == 0
