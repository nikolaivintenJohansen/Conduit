"""OAuth2 Authorization Code + PKCE / OIDC core (Phase 3).

Issues short-lived authorization codes, exchanges them for access/id/refresh
tokens, and rotates refresh tokens. Tokens are signed with the existing
HS256 `jwt_secret` (RS256/JWKS-asymmetric is tracked as a Stage 5 hardening
item). Opaque refresh tokens are stored only as HMAC hashes.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from jose import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.shared.config import get_settings
from services.shared.models import (
    AppInstall,
    OAuthAuthorizationCode,
    OAuthRefreshToken,
    User,
)
from services.wallet.app_registrations import (
    get_app_registration_by_client_id,
    verify_client_secret,
)
from services.wallet.keys import hash_key


class OAuthError(Exception):
    pass


class InvalidGrantError(OAuthError):
    pass


class InvalidClientError(OAuthError):
    pass


class InvalidTokenError(OAuthError):
    pass


@dataclass(frozen=True)
class AuthorizationCodeResult:
    code: str
    record: OAuthAuthorizationCode


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    id_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"


def _now() -> datetime:
    return datetime.now(UTC)


def _scopes_list(scopes: list[str] | None) -> list[str]:
    settings = get_settings()
    if not scopes:
        return settings.oauth_default_scopes.split()
    return scopes


def _verify_pkce(verifier: str, challenge: str, method: str) -> bool:
    if method == "plain":
        return secrets.compare_digest(verifier, challenge)
    if method == "S256":
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        computed = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return secrets.compare_digest(computed, challenge)
    return False


def create_authorization_code(
    session: Session,
    *,
    client_id: str,
    user_id: UUID,
    app_install_id: UUID | None,
    redirect_uri: str,
    scopes: list[str] | None = None,
    pkce_code_challenge: str | None = None,
    pkce_code_challenge_method: str = "S256",
) -> AuthorizationCodeResult:
    settings = get_settings()
    plaintext = secrets.token_urlsafe(32)
    record = OAuthAuthorizationCode(
        client_id=client_id,
        user_id=user_id,
        app_install_id=app_install_id,
        code_hash=hash_key(plaintext),
        redirect_uri=redirect_uri,
        scopes=_scopes_list(scopes),
        pkce_code_challenge=pkce_code_challenge,
        pkce_code_challenge_method=pkce_code_challenge_method,
        expires_at=_now() + timedelta(seconds=settings.oauth_code_expiry_seconds),
    )
    session.add(record)
    session.flush()
    return AuthorizationCodeResult(code=plaintext, record=record)


def _find_code_by_plaintext(session: Session, code: str) -> OAuthAuthorizationCode | None:
    code_hash = hash_key(code)
    return session.scalar(
        select(OAuthAuthorizationCode).where(OAuthAuthorizationCode.code_hash == code_hash)
    )


def _issue_access_token(
    user: User, client_id: str, app_install_id: UUID | None, scopes: list[str]
) -> str:
    settings = get_settings()
    now = _now()
    exp = now + timedelta(seconds=settings.oauth_access_token_expiry_seconds)
    payload = {
        "sub": str(user.id),
        "app_install_id": str(app_install_id) if app_install_id else None,
        "scope": " ".join(scopes),
        "iss": settings.oidc_issuer,
        "aud": client_id,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _issue_id_token(user: User, client_id: str) -> str:
    settings = get_settings()
    now = _now()
    exp = now + timedelta(seconds=settings.oauth_access_token_expiry_seconds)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "email_verified": user.email_verified_at is not None,
        "name": user.display_name,
        "iss": settings.oidc_issuer,
        "aud": client_id,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _issue_refresh_token(
    session: Session,
    *,
    client_id: str,
    user_id: UUID,
    app_install_id: UUID | None,
    scopes: list[str],
) -> str:
    settings = get_settings()
    plaintext = secrets.token_urlsafe(32)
    record = OAuthRefreshToken(
        client_id=client_id,
        user_id=user_id,
        app_install_id=app_install_id,
        token_hash=hash_key(plaintext),
        scopes=scopes,
        expires_at=_now() + timedelta(seconds=settings.oauth_refresh_token_expiry_seconds),
    )
    session.add(record)
    session.flush()
    return plaintext


def exchange_code_for_tokens(
    session: Session,
    *,
    code: str,
    code_verifier: str | None,
    client_id: str,
    client_secret: str | None,
    redirect_uri: str,
) -> TokenSet:
    record = _find_code_by_plaintext(session, code)
    if record is None:
        raise InvalidGrantError("unknown authorization code")
    if record.used_at is not None:
        raise InvalidGrantError("authorization code already used")
    if _now() > record.expires_at:
        raise InvalidGrantError("authorization code expired")
    if record.client_id != client_id:
        raise InvalidGrantError("client_id mismatch")
    if record.redirect_uri != redirect_uri:
        raise InvalidGrantError("redirect_uri mismatch")

    reg = get_app_registration_by_client_id(session, client_id)
    if reg is None or not reg.is_active:
        raise InvalidClientError("unknown or inactive client")
    if client_secret is not None and not verify_client_secret(reg, client_secret):
        raise InvalidClientError("invalid client secret")

    if record.pkce_code_challenge:
        if not code_verifier or not _verify_pkce(
            code_verifier, record.pkce_code_challenge, record.pkce_code_challenge_method
        ):
            raise InvalidGrantError("PKCE verification failed")

    user = session.get(User, record.user_id)
    if user is None:
        raise InvalidGrantError("user not found")

    # Mark code used before issuing tokens to prevent replay.
    record.used_at = _now()

    access_token = _issue_access_token(user, client_id, record.app_install_id, record.scopes)
    id_token = _issue_id_token(user, client_id)
    refresh_token = _issue_refresh_token(
        session,
        client_id=client_id,
        user_id=user.id,
        app_install_id=record.app_install_id,
        scopes=record.scopes,
    )
    session.flush()

    settings = get_settings()
    return TokenSet(
        access_token=access_token,
        id_token=id_token,
        refresh_token=refresh_token,
        expires_in=settings.oauth_access_token_expiry_seconds,
    )


def _find_refresh_token(session: Session, plaintext: str) -> OAuthRefreshToken | None:
    return session.scalar(
        select(OAuthRefreshToken).where(OAuthRefreshToken.token_hash == hash_key(plaintext))
    )


def refresh_access_token(
    session: Session,
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str | None,
) -> TokenSet:
    record = _find_refresh_token(session, refresh_token)
    if record is None:
        raise InvalidGrantError("unknown refresh token")
    if record.revoked_at is not None:
        raise InvalidGrantError("refresh token revoked")
    if _now() > record.expires_at:
        raise InvalidGrantError("refresh token expired")
    if record.client_id != client_id:
        raise InvalidGrantError("client_id mismatch")

    reg = get_app_registration_by_client_id(session, client_id)
    if reg is None or not reg.is_active:
        raise InvalidClientError("unknown or inactive client")
    if client_secret is not None and not verify_client_secret(reg, client_secret):
        raise InvalidClientError("invalid client secret")

    user = session.get(User, record.user_id)
    if user is None:
        raise InvalidGrantError("user not found")

    # Rotate: revoke the presented token, issue a new one in the same transaction.
    record.revoked_at = _now()
    new_refresh = _issue_refresh_token(
        session,
        client_id=client_id,
        user_id=user.id,
        app_install_id=record.app_install_id,
        scopes=record.scopes,
    )

    access_token = _issue_access_token(user, client_id, record.app_install_id, record.scopes)
    id_token = _issue_id_token(user, client_id)
    session.flush()

    settings = get_settings()
    return TokenSet(
        access_token=access_token,
        id_token=id_token,
        refresh_token=new_refresh,
        expires_in=settings.oauth_access_token_expiry_seconds,
    )


def revoke_refresh_token(session: Session, plaintext: str) -> bool:
    record = _find_refresh_token(session, plaintext)
    if record is None or record.revoked_at is not None:
        return False
    record.revoked_at = _now()
    session.flush()
    return True


def revoke_tokens_for_install(session: Session, app_install_id: UUID) -> int:
    tokens = list(
        session.scalars(
            select(OAuthRefreshToken).where(
                OAuthRefreshToken.app_install_id == app_install_id,
                OAuthRefreshToken.revoked_at.is_(None),
            )
        ).all()
    )
    for token in tokens:
        token.revoked_at = _now()
    session.flush()
    return len(tokens)


def decode_access_token(token: str) -> dict:
    """Validate and decode an app access token. Raises InvalidTokenError on failure."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.oidc_issuer,
            options={"verify_aud": False},
        )
    except Exception as exc:
        raise InvalidTokenError("invalid access token") from exc
    if payload.get("typ") != "access":
        raise InvalidTokenError("not an access token")
    return payload


def get_install_for_access_token(session: Session, payload: dict) -> AppInstall | None:
    install_id = payload.get("app_install_id")
    if not install_id:
        return None
    try:
        uuid = UUID(str(install_id))
    except ValueError:
        return None
    return session.get(AppInstall, uuid)


def build_oidc_discovery(issuer: str | None = None) -> dict:
    settings = get_settings()
    iss = issuer or settings.oidc_issuer
    return {
        "issuer": iss,
        "authorization_endpoint": f"{iss}/oauth/authorize",
        "token_endpoint": f"{iss}/oauth/token",
        "userinfo_endpoint": f"{iss}/oauth/userinfo",
        "jwks_uri": f"{iss}/oauth/jwks",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["HS256"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
        "code_challenge_methods_supported": ["S256", "plain"],
        "scopes_supported": settings.oauth_default_scopes.split(),
    }


def build_jwks() -> dict:
    # HS256 uses a shared secret, not an asymmetric key. We expose a documented
    # stub so standards-compliant clients can fetch jwks_uri; RS256 keys land in
    # Stage 5. See docs/07-implementation-phases.md "Out of scope".
    return {"keys": []}


def build_userinfo(session: Session, access_token: str) -> dict:
    payload = decode_access_token(access_token)
    user = session.get(User, UUID(str(payload["sub"])))
    if user is None:
        raise InvalidTokenError("user not found")
    info = {
        "sub": str(user.id),
        "email": user.email,
        "email_verified": user.email_verified_at is not None,
    }
    if user.display_name:
        info["name"] = user.display_name
    install = get_install_for_access_token(session, payload)
    if install is not None:
        info["app_install_id"] = str(install.id)
        info["allowance_spent_microdollars"] = install.allowance_spent_microdollars
        info["spend_limit_microdollars"] = install.spend_limit_microdollars
    return info
