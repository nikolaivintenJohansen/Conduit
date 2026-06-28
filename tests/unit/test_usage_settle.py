"""Phase 5 hardening: async settle soft overage tagging on the slow path."""

from __future__ import annotations

from uuid import uuid4

from services.shared.models import Wallet
from services.wallet.ledger import debit_wallet
from services.wallet.usage import settle_usage_direct


def test_settle_usage_direct_tags_spend_limit_overage(db_session, sandbox_user):
    wallet = Wallet(
        user_id=sandbox_user.id,
        balance_microdollars=5_000_000,
        spend_limit_microdollars=200_000,
    )
    db_session.add(wallet)
    db_session.flush()

    # Seed monthly spend near the cap with a direct debit that skips the limit check.
    debit_wallet(
        db_session,
        wallet.id,
        150_000,
        idempotency_key=f"seed:{uuid4()}",
        skip_spend_limit_check=True,
    )
    db_session.flush()

    result = settle_usage_direct(
        db_session,
        request_id=f"req-overage-{uuid4().hex[:8]}",
        user_id=sandbox_user.id,
        wallet_id=wallet.id,
        model="gpt-4o-mini",
        input_tokens=120,
        output_tokens=80,
        base_cost_microdollars=10_000,
        charged_microdollars=100_000,
    )

    assert result.created is True
    metadata = result.usage_event.metadata_json or {}
    assert metadata.get("spend_limit_overage") is True
    assert metadata.get("spend_limit_microdollars") == 200_000
    assert metadata.get("monthly_spend_microdollars") == 250_000


def test_settle_usage_direct_no_overage_tag_when_under_limit(db_session, sandbox_user):
    wallet = Wallet(
        user_id=sandbox_user.id,
        balance_microdollars=5_000_000,
        spend_limit_microdollars=1_000_000,
    )
    db_session.add(wallet)
    db_session.flush()

    result = settle_usage_direct(
        db_session,
        request_id=f"req-ok-{uuid4().hex[:8]}",
        user_id=sandbox_user.id,
        wallet_id=wallet.id,
        model="gpt-4o-mini",
        input_tokens=120,
        output_tokens=80,
        base_cost_microdollars=10_000,
        charged_microdollars=50_000,
    )

    assert result.created is True
    assert "spend_limit_overage" not in (result.usage_event.metadata_json or {})


def test_settle_usage_direct_no_tag_when_no_limit_configured(db_session, sandbox_user):
    wallet = Wallet(user_id=sandbox_user.id, balance_microdollars=5_000_000)
    db_session.add(wallet)
    db_session.flush()

    result = settle_usage_direct(
        db_session,
        request_id=f"req-nolimit-{uuid4().hex[:8]}",
        user_id=sandbox_user.id,
        wallet_id=wallet.id,
        model="gpt-4o-mini",
        input_tokens=120,
        output_tokens=80,
        base_cost_microdollars=10_000,
        charged_microdollars=50_000,
    )

    assert result.created is True
    assert "spend_limit_overage" not in (result.usage_event.metadata_json or {})
