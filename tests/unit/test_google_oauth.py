from uuid import uuid4

from services.shared.models import OAuthIdentity
from services.wallet.auth import get_or_create_oauth_user, get_user_by_email


def test_get_or_create_oauth_user_creates_new(db_session):
    email = f"g-{uuid4()}@example.com"
    user = get_or_create_oauth_user(
        db_session,
        provider="google",
        provider_sub="google-sub-1",
        email=email,
        display_name="Google User",
    )

    assert user.email == email
    assert user.password_hash is None
    assert user.display_name == "Google User"
    identities = db_session.query(OAuthIdentity).filter_by(user_id=user.id).all()
    assert len(identities) == 1
    assert identities[0].provider == "google"


def test_get_or_create_oauth_user_is_idempotent(db_session):
    email = f"g-{uuid4()}@example.com"
    first = get_or_create_oauth_user(
        db_session, provider="google", provider_sub="google-sub-2", email=email
    )
    second = get_or_create_oauth_user(
        db_session, provider="google", provider_sub="google-sub-2", email=email
    )

    assert first.id == second.id
    identities = db_session.query(OAuthIdentity).filter_by(provider="google").all()
    assert len(identities) == 1


def test_get_or_create_oauth_user_links_existing_email(db_session):
    email = f"existing-{uuid4()}@example.com"
    existing = get_or_create_oauth_user(
        db_session, provider="google", provider_sub="sub-a", email=email
    )

    # A different Google identity on the same email links to the same user.
    linked = get_or_create_oauth_user(
        db_session, provider="google", provider_sub="sub-b", email=email
    )

    assert linked.id == existing.id
    assert get_user_by_email(db_session, email).id == existing.id
    identities = db_session.query(OAuthIdentity).filter_by(user_id=existing.id).all()
    assert len(identities) == 2
