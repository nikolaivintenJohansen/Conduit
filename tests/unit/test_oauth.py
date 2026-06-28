import base64
import hashlib
from uuid import uuid4

import pytest

from services.shared.models import PartnerAccount
from services.wallet.app_registrations import create_app_registration
from services.wallet.apps import connect_app
from services.wallet.auth import create_user
from services.wallet.oauth import (
    InvalidGrantError,
    build_jwks,
    build_oidc_discovery,
    build_userinfo,
    create_authorization_code,
    decode_access_token,
    exchange_code_for_tokens,
    refresh_access_token,
    revoke_refresh_token,
    revoke_tokens_for_install,
)


@pytest.fixture
def user_app_install(db_session):
    user = create_user(db_session, f"o-{uuid4()}@example.com", "super-password-1")
    partner = PartnerAccount(name="P", slug=f"p-{uuid4().hex[:8]}")
    db_session.add(partner)
    db_session.flush()
    created = create_app_registration(
        db_session,
        partner_account_id=partner.id,
        name="OAuthApp",
        redirect_uris=["https://app.example.com/cb"],
    )
    install = connect_app(
        db_session,
        user_id=user.id,
        client_id=created.record.client_id,
        spend_limit_microdollars=5_000_000,
    )
    return user, created, install


def _pkce_pair():
    verifier = "v" * 43
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    return verifier, challenge


def test_exchange_code_with_pkce_issues_tokens(db_session, user_app_install):
    user, created, install = user_app_install
    verifier, challenge = _pkce_pair()
    code = create_authorization_code(
        db_session,
        client_id=created.record.client_id,
        user_id=user.id,
        app_install_id=install.id,
        redirect_uri="https://app.example.com/cb",
        pkce_code_challenge=challenge,
    )

    tokens = exchange_code_for_tokens(
        db_session,
        code=code.code,
        code_verifier=verifier,
        client_id=created.record.client_id,
        client_secret=created.client_secret,
        redirect_uri="https://app.example.com/cb",
    )

    assert tokens.token_type == "Bearer"
    assert tokens.access_token
    assert tokens.id_token
    assert tokens.refresh_token
    assert tokens.expires_in > 0

    payload = decode_access_token(tokens.access_token)
    assert payload["sub"] == str(user.id)
    assert payload["app_install_id"] == str(install.id)
    assert payload["typ"] == "access"
    assert payload["aud"] == created.record.client_id


def test_exchange_rejects_pkce_mismatch(db_session, user_app_install):
    user, created, install = user_app_install
    _, challenge = _pkce_pair()
    code = create_authorization_code(
        db_session,
        client_id=created.record.client_id,
        user_id=user.id,
        app_install_id=install.id,
        redirect_uri="https://app.example.com/cb",
        pkce_code_challenge=challenge,
    )

    with pytest.raises(InvalidGrantError):
        exchange_code_for_tokens(
            db_session,
            code=code.code,
            code_verifier="wrong-verifier",
            client_id=created.record.client_id,
            client_secret=created.client_secret,
            redirect_uri="https://app.example.com/cb",
        )


def test_exchange_rejects_replayed_code(db_session, user_app_install):
    user, created, install = user_app_install
    code = create_authorization_code(
        db_session,
        client_id=created.record.client_id,
        user_id=user.id,
        app_install_id=install.id,
        redirect_uri="https://app.example.com/cb",
    )
    kwargs = dict(
        code=code.code,
        code_verifier=None,
        client_id=created.record.client_id,
        client_secret=created.client_secret,
        redirect_uri="https://app.example.com/cb",
    )
    exchange_code_for_tokens(db_session, **kwargs)
    with pytest.raises(InvalidGrantError):
        exchange_code_for_tokens(db_session, **kwargs)


def test_refresh_token_rotation_revokes_old(db_session, user_app_install):
    user, created, install = user_app_install
    code = create_authorization_code(
        db_session,
        client_id=created.record.client_id,
        user_id=user.id,
        app_install_id=install.id,
        redirect_uri="https://app.example.com/cb",
    )
    tokens = exchange_code_for_tokens(
        db_session,
        code=code.code,
        code_verifier=None,
        client_id=created.record.client_id,
        client_secret=created.client_secret,
        redirect_uri="https://app.example.com/cb",
    )

    refreshed = refresh_access_token(
        db_session,
        refresh_token=tokens.refresh_token,
        client_id=created.record.client_id,
        client_secret=created.client_secret,
    )
    assert refreshed.refresh_token != tokens.refresh_token
    assert decode_access_token(refreshed.access_token)["sub"] == str(user.id)

    # Old refresh token is now revoked.
    with pytest.raises(InvalidGrantError):
        refresh_access_token(
            db_session,
            refresh_token=tokens.refresh_token,
            client_id=created.record.client_id,
            client_secret=created.client_secret,
        )


def test_revoke_tokens_for_install(db_session, user_app_install):
    user, created, install = user_app_install
    code = create_authorization_code(
        db_session,
        client_id=created.record.client_id,
        user_id=user.id,
        app_install_id=install.id,
        redirect_uri="https://app.example.com/cb",
    )
    tokens = exchange_code_for_tokens(
        db_session,
        code=code.code,
        code_verifier=None,
        client_id=created.record.client_id,
        client_secret=created.client_secret,
        redirect_uri="https://app.example.com/cb",
    )

    assert revoke_tokens_for_install(db_session, install.id) == 1
    assert revoke_refresh_token(db_session, tokens.refresh_token) is False


def test_discovery_and_jwks_shape():
    discovery = build_oidc_discovery("https://api.example.com")
    assert discovery["issuer"] == "https://api.example.com"
    assert discovery["authorization_endpoint"].endswith("/oauth/authorize")
    assert discovery["token_endpoint"].endswith("/oauth/token")
    assert "S256" in discovery["code_challenge_methods_supported"]
    assert build_jwks() == {"keys": []}


def test_userinfo_returns_profile_and_install(db_session, user_app_install):
    user, created, install = user_app_install
    code = create_authorization_code(
        db_session,
        client_id=created.record.client_id,
        user_id=user.id,
        app_install_id=install.id,
        redirect_uri="https://app.example.com/cb",
    )
    tokens = exchange_code_for_tokens(
        db_session,
        code=code.code,
        code_verifier=None,
        client_id=created.record.client_id,
        client_secret=created.client_secret,
        redirect_uri="https://app.example.com/cb",
    )

    info = build_userinfo(db_session, tokens.access_token)
    assert info["sub"] == str(user.id)
    assert info["email"] == user.email
    assert info["app_install_id"] == str(install.id)
