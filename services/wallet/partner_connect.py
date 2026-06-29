"""Stripe Connect onboarding for partner accounts (Phase 7.1).

Creates a Connect Express account per partner, issues an AccountLink onboarding
URL, and stores the account's capabilities so the settlement runner can decide
whether a partner is ready to receive payouts. The ``account.updated`` webhook
refreshes capabilities as the partner completes onboarding.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import stripe
from sqlalchemy.orm import Session

from services.shared.config import get_settings
from services.shared.models import PartnerAccount

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OnboardingResult:
    partner: PartnerAccount
    stripe_connect_id: str
    onboarding_url: str


@dataclass(frozen=True)
class ConnectStatus:
    partner: PartnerAccount
    stripe_connect_id: str | None
    charges_enabled: bool
    details_submitted: bool
    payouts_enabled: bool
    capabilities: dict


def _configure_stripe() -> None:
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise RuntimeError("Stripe is not configured")
    stripe.api_key = settings.stripe_secret_key


def begin_onboarding(
    session: Session,
    partner: PartnerAccount,
    *,
    return_url: str,
    refresh_url: str,
    stripe_client=None,
) -> OnboardingResult:
    """Create or reuse a Connect Express account and return an onboarding URL."""
    client = stripe_client if stripe_client is not None else stripe
    if stripe_client is None:
        _configure_stripe()

    if not partner.stripe_connect_id:
        account = client.Account.create(
            type="express",
            metadata={"partner_account_id": str(partner.id), "partner_slug": partner.slug},
        )
        partner.stripe_connect_id = account.id
        session.flush()

    link = client.AccountLink.create(
        account=partner.stripe_connect_id,
        return_url=return_url,
        refresh_url=refresh_url,
        type="account_onboarding",
    )
    if not link.url:
        raise RuntimeError("Stripe AccountLink missing URL")
    return OnboardingResult(
        partner=partner,
        stripe_connect_id=partner.stripe_connect_id,
        onboarding_url=link.url,
    )


def get_connect_status(
    session: Session,
    partner: PartnerAccount,
    *,
    stripe_client=None,
) -> ConnectStatus:
    """Read the partner's Connect account status (live Stripe call)."""
    if not partner.stripe_connect_id:
        return ConnectStatus(
            partner=partner,
            stripe_connect_id=None,
            charges_enabled=False,
            details_submitted=False,
            payouts_enabled=False,
            capabilities=dict(partner.stripe_capabilities_json or {}),
        )

    client = stripe_client if stripe_client is not None else stripe
    if stripe_client is None:
        _configure_stripe()

    account = client.Account.retrieve(partner.stripe_connect_id)
    _store_capabilities(session, partner, account)
    return ConnectStatus(
        partner=partner,
        stripe_connect_id=partner.stripe_connect_id,
        charges_enabled=bool(getattr(account, "charges_enabled", False)),
        details_submitted=bool(getattr(account, "details_submitted", False)),
        payouts_enabled=bool(getattr(account, "payouts_enabled", False)),
        capabilities=dict(partner.stripe_capabilities_json or {}),
    )


def refresh_capabilities_from_event(
    session: Session,
    partner: PartnerAccount,
    account_obj,
) -> PartnerAccount | None:
    """Update stored capabilities from an ``account.updated`` webhook object."""
    return _store_capabilities(session, partner, account_obj)


def refresh_partner_for_account(
    session: Session, stripe_account_id: str, account_obj
) -> PartnerAccount | None:
    """Find the partner linked to a Stripe Connect account and refresh capabilities."""
    from sqlalchemy import select

    partner = session.scalar(
        select(PartnerAccount).where(PartnerAccount.stripe_connect_id == stripe_account_id)
    )
    if partner is None:
        return None
    return _store_capabilities(session, partner, account_obj)


def _store_capabilities(
    session: Session, partner: PartnerAccount, account_obj
) -> PartnerAccount | None:
    raw_caps = getattr(account_obj, "capabilities", None)
    capabilities: dict = {}
    if raw_caps:
        capabilities = dict(raw_caps) if not isinstance(raw_caps, dict) else dict(raw_caps)
    partner.stripe_capabilities_json = {
        "charges_enabled": bool(getattr(account_obj, "charges_enabled", False)),
        "details_submitted": bool(getattr(account_obj, "details_submitted", False)),
        "payouts_enabled": bool(getattr(account_obj, "payouts_enabled", False)),
        "capabilities": capabilities,
    }
    session.flush()
    return partner
