"""Google OIDC login helpers (Phase 3).

Exchanges an authorization code for Google tokens and fetches the authenticated
user's profile from Google's userinfo endpoint. The wallet never sees Google
credentials — only the profile claims.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    with _client() as client:
        url, _ = client.create_authorization_url(
            GOOGLE_DISCOVERY_URL,
            redirect_uri=settings.google_oauth_redirect_url,
            state=state,
        )
        return url


def exchange_code_and_profile(code: str) -> GoogleProfile:
    settings = get_settings()
    with _client() as client:
        token = client.fetch_token(
            GOOGLE_DISCOVERY_URL,
            redirect_uri=settings.google_oauth_redirect_url,
            code=code,
            grant_type="authorization_code",
        )
        access_token = token.get("access_token")
        if not access_token:
            raise GoogleOAuthError("Google token response missing access_token")

        discovery = client.get(GOOGLE_DISCOVERY_URL).json()
        userinfo_endpoint = discovery.get("userinfo_endpoint")
        if not userinfo_endpoint:
            raise GoogleOAuthError("Google discovery missing userinfo_endpoint")

        profile = client.get(
            userinfo_endpoint, headers={"Authorization": f"Bearer {access_token}"}
        ).json()

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
