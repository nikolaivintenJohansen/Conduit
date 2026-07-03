from uuid import uuid4

import pytest

from services.shared.config import get_settings
from services.shared.models import OAuthIdentity
from services.wallet import google_oauth
from services.wallet.auth import get_or_create_oauth_user, get_user_by_email


def test_authorization_url_uses_resolved_auth_endpoint(settings_env, monkeypatch):
    # Google's consent screen lives at the authorization_endpoint resolved from the
    # discovery document — NOT at the discovery URL itself.
    get_settings.cache_clear()
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "GOCSPX-test-secret")
    monkeypatch.setenv(
        "GOOGLE_OAUTH_REDIRECT_URL", "http://localhost:3000/auth/google/callback"
    )
    get_settings.cache_clear()

    fake_auth_ep = "https://accounts.google.com/o/oauth2/v2/auth"
    monkeypatch.setattr(
        google_oauth,
        "_get_discovery",
        lambda: {
            "authorization_endpoint": fake_auth_ep,
            "token_endpoint": "https://oauth2.googleapis.com/token",
            "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
        },
    )

    url = google_oauth.authorization_url("my-state")

    assert url.startswith(fake_auth_ep)
    assert "client_id=test-client-id.apps.googleusercontent.com" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Fauth%2Fgoogle%2Fcallback" in url
    assert "state=my-state" in url
    assert ".well-known/openid-configuration" not in url


def test_authorization_url_unconfigured_raises(settings_env, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "")
    get_settings.cache_clear()
    with pytest.raises(google_oauth.GoogleNotConfiguredError):
        google_oauth.authorization_url("state")


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
