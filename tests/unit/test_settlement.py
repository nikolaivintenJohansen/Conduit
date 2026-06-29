"""Unit tests for batch settlement (Phase 7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from services.shared.models import LedgerEntry, PartnerAccount, SettlementBatch, UsageEvent
from services.wallet import settlement as settlement_service


class FakeTransfer:
    def __init__(self, transfer_id: str = "tr_test_1") -> None:
        self.id = transfer_id


class FakeTransfers:
    def __init__(self, transfer_id: str = "tr_test_1", fail: bool = False) -> None:
        self._base = transfer_id
        self._counter = 0
        self.fail = fail
        self.created: list[dict] = []

    def create(self, **kwargs):  # noqa: ANN003 — mirrors stripe.Transfer.create
        if self.fail:
            raise RuntimeError("stripe transfer exploded")
        self._counter += 1
        self.created.append(kwargs)
        transfer_id = self._base if self._counter == 1 else f"{self._base}_{self._counter}"
        return FakeTransfer(transfer_id)


class FakeStripe:
    def __init__(self, transfer_id: str = "tr_test_1", fail: bool = False) -> None:
        self.Transfer = FakeTransfers(transfer_id=transfer_id, fail=fail)


@pytest.fixture
def settlement_partner(db_session) -> PartnerAccount:
    partner = PartnerAccount(
        name="Settlement Partner",
        slug=f"settle-{uuid4().hex[:8]}",
        stripe_connect_id="acct_test_connect_1",
    )
    db_session.add(partner)
    db_session.flush()
    return partner


def _seed_usage(
    db_session,
    *,
    partner: PartnerAccount,
    user_id,
    wallet_id,
    count: int,
    charged: int = 2_000_000,
    fee: int = 200_000,
    base: int = 1_000_000,
    margin: int = 800_000,
) -> list[UsageEvent]:
    events = []
    seeded_at = datetime.now(UTC) - timedelta(minutes=5)
    for i in range(count):
        events.append(
            UsageEvent(
                request_id=f"req-{partner.slug}-{i}-{uuid4().hex[:6]}",
                user_id=user_id,
                wallet_id=wallet_id,
                model="gpt-4o-mini",
                provider="openai",
                input_tokens=100,
                output_tokens=50,
                base_cost_microdollars=base,
                charged_microdollars=charged,
                platform_fee_microdollars=fee,
                partner_margin_microdollars=margin,
                partner_account_id=partner.id,
                status="completed",
                created_at=seeded_at,
            )
        )
    db_session.add_all(events)
    db_session.flush()
    return events


def test_aggregate_pending_sums_pending_events(
    db_session, sandbox_user, sandbox_wallet, settlement_partner
):
    _seed_usage(db_session, partner=settlement_partner, user_id=sandbox_user.id, wallet_id=sandbox_wallet.id, count=3)
    agg = settlement_service.aggregate_pending(db_session, settlement_partner.id)
    assert agg.event_count == 3
    assert agg.gross_usage_microdollars == 6_000_000
    assert agg.platform_fee_microdollars == 600_000
    assert agg.partner_payout_microdollars == 5_400_000


def test_settle_partner_clears_events_and_writes_ledger(
    db_session, sandbox_user, sandbox_wallet, settlement_partner
):
    events = _seed_usage(
        db_session, partner=settlement_partner, user_id=sandbox_user.id, wallet_id=sandbox_wallet.id, count=4
    )
    fake = FakeStripe(transfer_id="tr_clear_1")

    result = settlement_service.settle_partner(
        db_session, settlement_partner, stripe_client=fake
    )

    assert result.status == "cleared"
    assert result.event_count == 4
    assert result.payout_microdollars == 8_000_000 - 800_000

    batch = db_session.get(SettlementBatch, result.batch.id)
    assert batch.status == "cleared"
    assert batch.stripe_transfer_id == "tr_clear_1"
    assert batch.event_count == 4
    assert batch.partner_payout_microdollars == 7_200_000

    db_session.expire_all()
    refreshed = [db_session.get(UsageEvent, e.id) for e in events]
    assert all(e.settlement_status == "cleared" for e in refreshed)
    assert all(e.settlement_batch_id == batch.id for e in refreshed)

    settlement_entries = list(
        db_session.scalars(
            select(LedgerEntry).where(LedgerEntry.reference_type == "settlement_batch")
        )
    )
    assert len(settlement_entries) == 1
    assert settlement_entries[0].amount_microdollars == batch.partner_payout_microdollars
    assert settlement_entries[0].reference_id == batch.id
    assert settlement_entries[0].entry_type == "settlement"


def test_settle_partner_idempotent_no_double_payout(
    db_session, sandbox_user, sandbox_wallet, settlement_partner
):
    _seed_usage(
        db_session, partner=settlement_partner, user_id=sandbox_user.id, wallet_id=sandbox_wallet.id, count=2
    )
    fake = FakeStripe(transfer_id="tr_idem_1")

    first = settlement_service.settle_partner(db_session, settlement_partner, stripe_client=fake)
    assert first.status == "cleared"

    # Re-run on the same transaction (simulating a same-day re-run with the same idem key).
    fake.Transfer.created.clear()
    second = settlement_service.settle_partner(db_session, settlement_partner, stripe_client=fake)

    assert second.status == "cleared"
    assert second.batch.id == first.batch.id
    # No new transfer was issued and no new ledger row was written.
    assert fake.Transfer.created == []
    entries = list(
        db_session.scalars(
            select(LedgerEntry).where(LedgerEntry.reference_type == "settlement_batch")
        )
    )
    assert len(entries) == 1


def test_settle_partner_failed_releases_events_back_to_pending(
    db_session, sandbox_user, sandbox_wallet, settlement_partner
):
    _seed_usage(
        db_session, partner=settlement_partner, user_id=sandbox_user.id, wallet_id=sandbox_wallet.id, count=3
    )
    fake = FakeStripe(fail=True)

    result = settlement_service.settle_partner(db_session, settlement_partner, stripe_client=fake)
    assert result.status == "failed"
    batch = db_session.get(SettlementBatch, result.batch.id)
    assert batch.status == "failed"
    assert batch.error_message is not None

    pending = settlement_service.aggregate_pending(db_session, settlement_partner.id)
    assert pending.event_count == 3  # events released back to pending

    # A subsequent successful run re-attempts and clears.
    ok_fake = FakeStripe(transfer_id="tr_retry_ok")
    retry = settlement_service.settle_partner(
        db_session, settlement_partner, stripe_client=ok_fake
    )
    assert retry.status == "cleared"
    assert retry.batch.id == batch.id  # same idempotency key reused
    refreshed_batch = db_session.get(SettlementBatch, batch.id)
    assert refreshed_batch.status == "cleared"


def test_settle_partner_skips_below_threshold(
    db_session, sandbox_user, sandbox_wallet, settlement_partner, settings_env, monkeypatch
):
    # One tiny event below the default $1.00 min payout.
    _seed_usage(
        db_session,
        partner=settlement_partner,
        user_id=sandbox_user.id,
        wallet_id=sandbox_wallet.id,
        count=1,
        charged=100_000,
        fee=10_000,
        base=50_000,
        margin=40_000,
    )
    monkeypatch.setenv("SETTLEMENT_MIN_PAYOUT_MICRODOLLARS", "1_000_000")
    from services.shared.config import get_settings
    get_settings.cache_clear()

    fake = FakeStripe()
    result = settlement_service.settle_partner(db_session, settlement_partner, stripe_client=fake)
    assert result.status == "skipped_below_threshold"
    assert fake.Transfer.created == []
    # No batch row created.
    batches = list(db_session.scalars(select(SettlementBatch)))
    assert batches == []


def test_settle_partner_skips_when_no_connect_id(db_session, sandbox_user, sandbox_wallet):
    partner = PartnerAccount(name="No Connect", slug=f"noconnect-{uuid4().hex[:8]}")
    db_session.add(partner)
    db_session.flush()
    _seed_usage(
        db_session, partner=partner, user_id=sandbox_user.id, wallet_id=sandbox_wallet.id, count=2
    )
    result = settlement_service.settle_partner(db_session, partner, stripe_client=FakeStripe())
    assert result.status == "skipped_no_connect"


def test_settle_partner_skips_empty(db_session, settlement_partner):
    result = settlement_service.settle_partner(
        db_session, settlement_partner, stripe_client=FakeStripe()
    )
    assert result.status == "skipped_empty"


def test_run_settlement_once_clears_multiple_partners(
    db_session, sandbox_user, sandbox_wallet
):
    p1 = PartnerAccount(name="P1", slug=f"p1-{uuid4().hex[:6]}", stripe_connect_id="acct_p1")
    p2 = PartnerAccount(name="P2", slug=f"p2-{uuid4().hex[:6]}", stripe_connect_id="acct_p2")
    db_session.add_all([p1, p2])
    db_session.flush()
    _seed_usage(db_session, partner=p1, user_id=sandbox_user.id, wallet_id=sandbox_wallet.id, count=2)
    _seed_usage(db_session, partner=p2, user_id=sandbox_user.id, wallet_id=sandbox_wallet.id, count=3)

    fake = FakeStripe(transfer_id="tr_multi")
    report = settlement_service.run_settlement_once(
        session=db_session, stripe_client=fake
    )
    assert len(report.cleared) == 2
    assert len(report.failed) == 0
    assert report.cleared[0].event_count + report.cleared[1].event_count == 5


def test_run_settlement_once_filter_by_partner_slug(
    db_session, sandbox_user, sandbox_wallet
):
    p1 = PartnerAccount(name="P1", slug="cursor", stripe_connect_id="acct_p1")
    p2 = PartnerAccount(name="P2", slug="other", stripe_connect_id="acct_p2")
    db_session.add_all([p1, p2])
    db_session.flush()
    _seed_usage(db_session, partner=p1, user_id=sandbox_user.id, wallet_id=sandbox_wallet.id, count=2)
    _seed_usage(db_session, partner=p2, user_id=sandbox_user.id, wallet_id=sandbox_wallet.id, count=2)

    report = settlement_service.run_settlement_once(
        session=db_session, partner_slug="cursor", stripe_client=FakeStripe()
    )
    assert len(report.results) == 1
    assert report.results[0].partner_slug == "cursor"
    assert report.results[0].status == "cleared"
