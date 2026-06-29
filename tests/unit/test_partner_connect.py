"""Unit tests for Stripe Connect onboarding (Phase 7.1)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from services.shared.models import PartnerAccount
from services.wallet import partner_connect
from services.wallet.partner_connect import (
    begin_onboarding,
    get_connect_status,
    refresh_partner_for_account,
)


class FakeAccount:
    def __init__(self, account_id: str = "acct_onboard_1") -> None:
        self.id = account_id


class FakeAccounts:
    def __init__(self, account_id: str = "acct_onboard_1") -> None:
        self.account_id = account_id
        self.created: list[dict] = []

    def create(self, **kwargs):  # noqa: ANN003
        self.created.append(kwargs)
        return FakeAccount(self.account_id)

    def retrieve(self, account_id: str):  # noqa: ANN001
        return SimpleNamespace(
            id=account_id,
            charges_enabled=True,
            details_submitted=True,
            payouts_enabled=False,
            capabilities={"transfers": "active", "card_payments": "active"},
        )


class FakeAccountLink:
    def __init__(self, url: str = "https://connect.stripe.com/onboard/abc") -> None:
        self.url = url


class FakeAccountLinks:
    def __init__(self, url: str = "https://connect.stripe.com/onboard/abc") -> None:
        self.url = url
        self.created: list[dict] = []

    def create(self, **kwargs):  # noqa: ANN003
        self.created.append(kwargs)
        return FakeAccountLink(self.url)


class FakeStripe:
    def __init__(self) -> None:
        self.Account = FakeAccounts()
        self.AccountLink = FakeAccountLinks()


@pytest.fixture
def connect_partner(db_session) -> PartnerAccount:
    partner = PartnerAccount(name="Connect Partner", slug=f"connect-{uuid4().hex[:8]}")
    db_session.add(partner)
    db_session.flush()
    return partner


def test_begin_onboarding_creates_account_and_returns_url(db_session, connect_partner):
    fake = FakeStripe()
    result = begin_onboarding(
        db_session,
        connect_partner,
        return_url="https://app.example.com/return",
        refresh_url="https://app.example.com/refresh",
        stripe_client=fake,
    )
    assert result.stripe_connect_id == "acct_onboard_1"
    assert result.onboarding_url.startswith("https://connect.stripe.com/")
    assert connect_partner.stripe_connect_id == "acct_onboard_1"
    assert fake.Account.created and fake.Account.created[0]["type"] == "express"


def test_begin_onboarding_reuses_existing_account(db_session, connect_partner):
    connect_partner.stripe_connect_id = "acct_existing_1"
    db_session.flush()
    fake = FakeStripe()
    result = begin_onboarding(
        db_session,
        connect_partner,
        return_url="https://app.example.com/return",
        refresh_url="https://app.example.com/refresh",
        stripe_client=fake,
    )
    assert result.stripe_connect_id == "acct_existing_1"
    # No new account created.
    assert fake.Account.created == []


def test_get_connect_status_stores_capabilities(db_session, connect_partner):
    connect_partner.stripe_connect_id = "acct_status_1"
    db_session.flush()
    fake = FakeStripe()
    status = get_connect_status(db_session, connect_partner, stripe_client=fake)
    assert status.charges_enabled is True
    assert status.details_submitted is True
    assert status.payouts_enabled is False
    assert status.capabilities["charges_enabled"] is True
    assert status.capabilities["capabilities"]["transfers"] == "active"
    refreshed = db_session.get(PartnerAccount, connect_partner.id)
    assert refreshed.stripe_capabilities_json["charges_enabled"] is True


def test_get_connect_status_without_account(db_session, connect_partner):
    status = get_connect_status(db_session, connect_partner, stripe_client=FakeStripe())
    assert status.stripe_connect_id is None
    assert status.charges_enabled is False
    assert status.payouts_enabled is False


def test_refresh_partner_for_account_updates_capabilities(db_session, connect_partner):
    connect_partner.stripe_connect_id = "acct_refresh_1"
    db_session.flush()
    account_obj = SimpleNamespace(
        id="acct_refresh_1",
        charges_enabled=False,
        details_submitted=True,
        payouts_enabled=True,
        capabilities={"transfers": "pending"},
    )
    updated = refresh_partner_for_account(db_session, "acct_refresh_1", account_obj)
    assert updated is not None
    assert updated.stripe_capabilities_json["payouts_enabled"] is True
    assert updated.stripe_capabilities_json["charges_enabled"] is False


def test_refresh_partner_for_account_unknown_account_noops(db_session):
    account_obj = SimpleNamespace(
        id="acct_unknown",
        charges_enabled=True,
        details_submitted=True,
        payouts_enabled=True,
        capabilities={},
    )
    assert refresh_partner_for_account(db_session, "acct_unknown", account_obj) is None
