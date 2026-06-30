from uuid import uuid4

import pytest

from services.shared.models import AppRegistration, OAuthRefreshToken, PartnerAccount
from services.wallet.apps import (
    AppNotFoundError,
    connect_app,
    get_install_for_user,
    has_allowance_available,
    list_connected_apps,
    revoke_app,
    update_allowance,
)
from services.wallet.auth import create_user


@pytest.fixture
def user_with_app(db_session):
    user = create_user(db_session, f"u-{uuid4()}@example.com", "super-password-1")
    partner = PartnerAccount(name="P", slug=f"p-{uuid4().hex[:8]}")
    db_session.add(partner)
    db_session.flush()
    reg = AppRegistration(
        partner_account_id=partner.id,
        name="DemoApp",
        client_id=f"conduit_{uuid4().hex}",
        client_secret_hash="hash",
        redirect_uris=["https://demo.example.com/cb"],
    )
    db_session.add(reg)
    db_session.flush()
    return user, reg


def test_connect_app_creates_install_with_allowance(db_session, user_with_app):
    user, reg = user_with_app
    install = connect_app(
        db_session,
        user_id=user.id,
        client_id=reg.client_id,
        spend_limit_microdollars=5_000_000,
    )

    assert install.id is not None
    assert install.spend_limit_microdollars == 5_000_000
    assert install.allowance_spent_microdollars == 0
    assert install.allowance_reset_period == "monthly"
    assert install.revoked_at is None
    assert install.app_registration_id == reg.id


def test_connect_app_reactivates_revoked_install(db_session, user_with_app):
    user, reg = user_with_app
    first = connect_app(
        db_session, user_id=user.id, client_id=reg.client_id, spend_limit_microdollars=1_000_000
    )
    revoke_app(db_session, user_id=user.id, install_id=first.id)
    assert first.revoked_at is not None

    second = connect_app(
        db_session, user_id=user.id, client_id=reg.client_id, spend_limit_microdollars=2_000_000
    )
    assert second.id == first.id
    assert second.revoked_at is None
    assert second.spend_limit_microdollars == 2_000_000


def test_connect_app_rejects_unknown_client(db_session, user_with_app):
    user, _ = user_with_app
    with pytest.raises(AppNotFoundError):
        connect_app(db_session, user_id=user.id, client_id="conduit_unknown")


def test_connect_app_rejects_negative_allowance(db_session, user_with_app):
    user, reg = user_with_app
    with pytest.raises(ValueError):
        connect_app(
            db_session, user_id=user.id, client_id=reg.client_id, spend_limit_microdollars=-1
        )


def test_update_allowance_and_revoke(db_session, user_with_app):
    user, reg = user_with_app
    install = connect_app(
        db_session, user_id=user.id, client_id=reg.client_id, spend_limit_microdollars=1_000_000
    )

    updated = update_allowance(
        db_session, user_id=user.id, install_id=install.id, spend_limit_microdollars=3_000_000
    )
    assert updated.spend_limit_microdollars == 3_000_000

    # Revoke also revokes bound refresh tokens.
    refresh = OAuthRefreshToken(
        client_id=reg.client_id,
        user_id=user.id,
        app_install_id=install.id,
        token_hash="hash-1",
        expires_at=__import__("datetime")
        .datetime.now(__import__("datetime").UTC)
        .replace(year=2099),
    )
    db_session.add(refresh)
    db_session.flush()

    revoked = revoke_app(db_session, user_id=user.id, install_id=install.id)
    assert revoked.revoked_at is not None
    db_session.refresh(refresh)
    assert refresh.revoked_at is not None

    # Allowance check fails after revoke.
    assert has_allowance_available(revoked, 0) is False


def test_has_allowance_available_enforces_limit(db_session, user_with_app):
    user, reg = user_with_app
    install = connect_app(
        db_session, user_id=user.id, client_id=reg.client_id, spend_limit_microdollars=1_000_000
    )
    install.allowance_spent_microdollars = 800_000
    db_session.flush()

    assert has_allowance_available(install, 100_000) is True
    assert has_allowance_available(install, 300_000) is False

    # No limit → always available.
    unlimited = connect_app(
        db_session, user_id=user.id, client_id=reg.client_id, spend_limit_microdollars=None
    )
    unlimited = get_install_for_user(db_session, user.id, unlimited.id)
    assert has_allowance_available(unlimited, 10_000_000) is True


def test_list_connected_apps(db_session, user_with_app):
    user, reg = user_with_app
    connect_app(
        db_session, user_id=user.id, client_id=reg.client_id, spend_limit_microdollars=500_000
    )
    connected = list_connected_apps(db_session, user.id)
    assert len(connected) == 1
    assert connected[0].registration.client_id == reg.client_id
