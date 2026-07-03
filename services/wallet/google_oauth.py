"""Google OIDC login helpers (Phase 3).

Exchanges an authorization code for Google tokens and fetches the authenticated
user's profile from Google's userinfo endpoint. The wallet never sees Google
credentials — only the profile claims.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from authlib.integrations.httpx_client import OAuth2Client

from services.shared.config import get_settings

GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"


@dataclass(frozen=True)
class GoogleProfile:
    sub: str
    email: str
    email_verified: bool
    name: str | None


class GoogleOAuthError(Exception):
    pass


class GoogleNotConfiguredError(GoogleOAuthError):
    pass


_discovery_cache: dict | None = None


def _get_discovery() -> dict:
    """Fetch (and cache) Google's OIDC discovery document.

    The discovery document is the source of truth for the authorization, token,
    and userinfo endpoints — Google's consent screen lives at
    ``authorization_endpoint``, NOT at the discovery URL itself. Google's
    endpoints are stable, so caching once per process avoids a network
    round-trip on every login. A plain httpx GET is used because the discovery
    document is public (no bearer token).
    """
    global _discovery_cache
    if _discovery_cache is not None:
        return _discovery_cache
    resp = httpx.get(GOOGLE_DISCOVERY_URL, timeout=10)
    resp.raise_for_status()
    _discovery_cache = resp.json()
    return _discovery_cache


def reset_discovery_cache() -> None:
    """Clear the cached discovery document (used by tests)."""
    global _discovery_cache
    _discovery_cache = None


def _client() -> OAuth2Client:
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise GoogleNotConfiguredError("Google OAuth is not configured")
    return OAuth2Client(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scope="openid email profile",
    )


def authorization_url(state: str) -> str:
    settings = get_settings()
    with _client() as client:  # raises GoogleNotConfiguredError if unconfigured
        discovery = _get_discovery()
        auth_ep = discovery.get("authorization_endpoint")
        if not auth_ep:
            raise GoogleOAuthError("Google discovery missing authorization_endpoint")
        url, _ = client.create_authorization_url(
            auth_ep,
            redirect_uri=settings.google_oauth_redirect_url,
            state=state,
        )
        return url


def exchange_code_and_profile(code: str) -> GoogleProfile:
    settings = get_settings()
    discovery = _get_discovery()
    token_ep = discovery.get("token_endpoint")
    userinfo_ep = discovery.get("userinfo_endpoint")
    if not token_ep or not userinfo_ep:
        raise GoogleOAuthError("Google discovery missing token or userinfo endpoint")
    if not settings.google_client_id or not settings.google_client_secret:
        raise GoogleNotConfiguredError("Google OAuth is not configured")

    try:
        resp = httpx.post(
            token_ep,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.google_oauth_redirect_url,
            },
            headers={"Accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        token = resp.json()
    except GoogleOAuthError:
        raise
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json()
        except ValueError:
            detail = exc.response.text
        raise GoogleOAuthError(f"Google token exchange failed: {detail}") from exc
    except Exception as exc:
        raise GoogleOAuthError(f"Google token exchange failed: {exc}") from exc

    access_token = token.get("access_token")
    if not access_token:
        raise GoogleOAuthError("Google token response missing access_token")

    # Fetch the userinfo profile with a plain httpx GET. authlib's OAuth2Client
    # auto-manages a bearer token on its own .get() and this authlib version
    # rejects the withhold_token kwarg, so a raw httpx request with an explicit
    # Authorization header is the robust path. Wrap failures in GoogleOAuthError
    # so the caller returns a proper 400 (with CORS) instead of an opaque 500.
    try:
        resp = httpx.get(
            userinfo_ep,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        profile = resp.json()
    except Exception as exc:
        raise GoogleOAuthError(f"Google userinfo request failed: {exc}") from exc

    sub = profile.get("sub")
    email = profile.get("email")
    if not sub or not email:
        raise GoogleOAuthError("Google profile missing sub or email")
    return GoogleProfile(
        sub=str(sub),
        email=str(email).lower(),
        email_verified=bool(profile.get("email_verified")),
        name=profile.get("name"),
    )
