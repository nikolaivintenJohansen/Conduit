"""OAuth2/OIDC HTTP endpoints + consent UI (Phase 3).

Root-mounted (no /wallet/v1 prefix) per docs/04-api-contracts.md §5. The
authorize/consent flow is JSON-driven so the hosted `consent.html` page and
partner SDKs can both drive it; the consent page reads params from the URL
query, fetches the descriptor, and submits the user's chosen spend limit.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Header, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from services.app.dashboard.routes import _static_file
from services.shared.config import get_settings
from services.shared.models import AppRegistration, User
from services.wallet.app_registrations import get_app_registration_by_client_id
from services.wallet.apps import AppNotActiveError, AppNotFoundError, connect_app
from services.wallet.deps import get_current_user, get_db
from services.wallet.oauth import (
    InvalidClientError,
    InvalidGrantError,
    InvalidTokenError,
    build_jwks,
    build_oidc_discovery,
    build_userinfo,
    create_authorization_code,
    exchange_code_for_tokens,
    refresh_access_token,
    revoke_refresh_token,
)

router = APIRouter(tags=["OAuth"])


# ---------------------------------------------------------------------------
# Discovery + JWKS
# ---------------------------------------------------------------------------


@router.get("/.well-known/openid-configuration")
def oidc_discovery() -> dict:
    return build_oidc_discovery()


@router.get("/oauth/jwks")
def jwks() -> dict:
    return build_jwks()


# ---------------------------------------------------------------------------
# Authorize + consent
# ---------------------------------------------------------------------------


class AuthorizeDescriptor(BaseModel):
    client_id: str
    redirect_uri: str
    response_type: str
    state: str | None = None
    scope: str
    code_challenge: str | None = None
    code_challenge_method: str = "S256"
    app_name: str
    app_logo_url: str | None = None
    requested_scopes: list[str]


def _validate_client(db: Session, client_id: str, redirect_uri: str) -> AppRegistration:
    reg = get_app_registration_by_client_id(db, client_id)
    if reg is None or not reg.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_client", "message": "Unknown or inactive client"}},
        )
    if redirect_uri not in reg.redirect_uris:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {"code": "invalid_redirect_uri", "message": "redirect_uri not registered"}
            },
        )
    return reg


@router.get("/oauth/authorize", response_model=AuthorizeDescriptor)
def authorize(
    client_id: str,
    redirect_uri: str,
    response_type: str = "code",
    state: str | None = None,
    scope: str | None = None,
    code_challenge: str | None = None,
    code_challenge_method: str = "S256",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuthorizeDescriptor:
    if response_type != "code":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "unsupported_response_type",
                    "message": "Only 'code' is supported",
                }
            },
        )
    reg = _validate_client(db, client_id, redirect_uri)
    settings = get_settings()
    requested = (scope or settings.oauth_default_scopes).split()
    return AuthorizeDescriptor(
        client_id=client_id,
        redirect_uri=redirect_uri,
        response_type=response_type,
        state=state,
        scope=scope or settings.oauth_default_scopes,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        app_name=reg.name,
        app_logo_url=reg.logo_url,
        requested_scopes=requested,
    )


class ConsentRequest(BaseModel):
    client_id: str
    redirect_uri: str
    state: str | None = None
    scope: str | None = None
    code_challenge: str | None = None
    code_challenge_method: str = "S256"
    spend_limit_microdollars: int | None = Field(default=None, ge=0)
    reset_period: str = "monthly"
    display_name: str | None = None


class ConsentResponse(BaseModel):
    redirect_uri: str
    code: str
    state: str | None = None


@router.post("/oauth/authorize/consent", response_model=ConsentResponse)
def consent(
    body: ConsentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConsentResponse:
    _validate_client(db, body.client_id, body.redirect_uri)

    try:
        install = connect_app(
            db,
            user_id=user.id,
            client_id=body.client_id,
            spend_limit_microdollars=body.spend_limit_microdollars,
            reset_period=body.reset_period,
            display_name=body.display_name,
        )
    except AppNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "app_not_found", "message": str(exc)}},
        ) from exc
    except AppNotActiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "app_not_active", "message": str(exc)}},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_allowance", "message": str(exc)}},
        ) from exc

    settings = get_settings()
    scopes = (body.scope or settings.oauth_default_scopes).split()
    issued = create_authorization_code(
        db,
        client_id=body.client_id,
        user_id=user.id,
        app_install_id=install.id,
        redirect_uri=body.redirect_uri,
        scopes=scopes,
        pkce_code_challenge=body.code_challenge,
        pkce_code_challenge_method=body.code_challenge_method,
    )

    # Build the redirect URL with code + state.
    separator = "&" if "?" in body.redirect_uri else "?"
    target = f"{body.redirect_uri}{separator}code={issued.code}"
    if body.state:
        target += f"&state={body.state}"
    return ConsentResponse(redirect_uri=target, code=issued.code, state=body.state)


# ---------------------------------------------------------------------------
# Token endpoint
# ---------------------------------------------------------------------------


class TokenResponse(BaseModel):
    access_token: str
    id_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    scope: str


class TokenErrorBody(BaseModel):
    error: str
    error_description: str | None = None


def _token_error(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"error": code, "error_description": message},
    )


@router.post(
    "/oauth/token",
    response_model=TokenResponse,
    responses={400: {"model": TokenErrorBody}},
)
def token(
    grant_type: str = Form(...),
    code: str | None = Form(default=None),
    code_verifier: str | None = Form(default=None),
    refresh_token: str | None = Form(default=None),
    redirect_uri: str | None = Form(default=None),
    client_id: str = Form(...),
    client_secret: str | None = Form(default=None),
    scope: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> TokenResponse:
    try:
        if grant_type == "authorization_code":
            if not code or not redirect_uri:
                raise _token_error("invalid_request", "code and redirect_uri required")
            tokens = exchange_code_for_tokens(
                db,
                code=code,
                code_verifier=code_verifier,
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
            )
        elif grant_type == "refresh_token":
            if not refresh_token:
                raise _token_error("invalid_request", "refresh_token required")
            tokens = refresh_access_token(
                db,
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
            )
        else:
            raise _token_error("unsupported_grant_type", f"grant_type {grant_type} not supported")
    except InvalidGrantError as exc:
        raise _token_error("invalid_grant", str(exc)) from exc
    except InvalidClientError as exc:
        raise _token_error("invalid_client", str(exc)) from exc

    return TokenResponse(
        access_token=tokens.access_token,
        id_token=tokens.id_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        scope=scope or " ".join(get_settings().oauth_default_scopes.split()),
    )


# ---------------------------------------------------------------------------
# Userinfo
# ---------------------------------------------------------------------------


@router.get("/oauth/userinfo")
def userinfo(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> dict:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "invalid_token", "message": "Bearer token required"}},
        )
    token = authorization.split(" ", 1)[1]
    try:
        info = build_userinfo(db, token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "invalid_token", "message": str(exc)}},
        ) from exc
    return info


# ---------------------------------------------------------------------------
# Token revocation (RFC 7009, minimal)
# ---------------------------------------------------------------------------


@router.post("/oauth/revoke", status_code=status.HTTP_200_OK)
def revoke(
    token: str = Form(...),
    db: Session = Depends(get_db),
) -> dict:
    revoke_refresh_token(db, token)
    return {}


# ---------------------------------------------------------------------------
# Consent UI
# ---------------------------------------------------------------------------


@router.get("/oauth/consent", include_in_schema=False)
def consent_page() -> FileResponse:
    return _static_file("consent.html")
