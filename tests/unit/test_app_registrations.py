from uuid import uuid4

import pytest

from services.shared.models import AppRegistration
from services.wallet.app_registrations import (
    create_app_registration,
    deactivate_app_registration,
    get_app_registration_by_client_id,
    list_app_registrations,
    rotate_client_secret,
    update_app_registration,
    verify_client_secret,
)


@pytest.fixture
def partner(db_session):
    from services.shared.models import PartnerAccount

    p = PartnerAccount(name="App Partner", slug=f"appslug-{uuid4().hex[:8]}")
    db_session.add(p)
    db_session.flush()
    return p


def test_create_app_registration_hashes_secret(db_session, partner):
    created = create_app_registration(
        db_session,
        partner_account_id=partner.id,
        name="Cursor",
        redirect_uris=["https://cursor.sh/callback"],
    )

    assert created.record.client_id.startswith("conduit_")
    assert created.client_secret
    assert created.record.client_secret_hash != created.client_secret
    assert created.record.is_active is True
    assert created.record.scopes == ["wallet:charge", "profile:read"]
    assert verify_client_secret(created.record, created.client_secret) is True


def test_create_app_registration_requires_redirect_uri(db_session, partner):
    with pytest.raises(ValueError):
        create_app_registration(
            db_session,
            partner_account_id=partner.id,
            name="NoRedirect",
            redirect_uris=[],
        )


def test_list_and_get_app_registration(db_session, partner):
    created = create_app_registration(
        db_session,
        partner_account_id=partner.id,
        name="App2",
        redirect_uris=["https://app2.example.com/cb"],
    )

    listed = list_app_registrations(db_session, partner_account_id=partner.id)
    assert len(listed) == 1
    assert listed[0].id == created.record.id

    fetched = get_app_registration_by_client_id(db_session, created.record.client_id)
    assert fetched is not None
    assert fetched.id == created.record.id


def test_rotate_client_secret_invalidates_old(db_session, partner):
    created = create_app_registration(
        db_session,
        partner_account_id=partner.id,
        name="Rotate",
        redirect_uris=["https://r.example.com/cb"],
    )
    old_secret = created.client_secret

    rotated = rotate_client_secret(db_session, created.record.id)
    assert rotated is not None
    assert rotated.client_secret != old_secret

    refreshed = db_session.get(AppRegistration, created.record.id)
    assert verify_client_secret(refreshed, rotated.client_secret) is True
    assert verify_client_secret(refreshed, old_secret) is False


def test_update_and_deactivate_app_registration(db_session, partner):
    created = create_app_registration(
        db_session,
        partner_account_id=partner.id,
        name="ToUpdate",
        redirect_uris=["https://u.example.com/cb"],
    )

    updated = update_app_registration(
        db_session, created.record.id, name="Renamed", is_active=False
    )
    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.is_active is False

    assert deactivate_app_registration(db_session, created.record.id) is True
    assert deactivate_app_registration(db_session, uuid4()) is False
