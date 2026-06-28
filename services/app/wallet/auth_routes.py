import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from services.shared.config import get_settings
from services.shared.models import Session as UserSession
from services.shared.models import User
from services.wallet.auth import (
    authenticate_user,
    create_user,
    get_or_create_oauth_user,
    get_user_by_email,
    invalidate_session,
    issue_session,
)
from services.wallet.balance import get_wallet_summary_for_user
from services.wallet.deps import get_current_session, get_current_user, get_db
from services.wallet.google_oauth import (
    GoogleNotConfiguredError,
    GoogleOAuthError,
    authorization_url,
    exchange_code_and_profile,
)
from services.wallet.keys import hash_key
from services.wallet.ledger import get_or_create_wallet

router = APIRouter(prefix="/wallet/v1", tags=["Auth"])

_OAUTH_STATE_COOKIE = "uaw_oauth_state"
_OAUTH_STATE_MAX_AGE = 600


def _sign_state(state: str) -> str:
    settings = get_settings()
    return f"{state}.{hash_key(state, pepper=settings.jwt_secret)}"


def _verify_state(state: str, signed: str) -> bool:
    if "." not in signed:
        return False
    expected = _sign_state(state)
    import hmac as _hmac

    return _hmac.compare_digest(expected, signed)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class MeResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None = None
    wallet_id: UUID
    balance_microdollars: int
    held_microdollars: int
    available_microdollars: int
    currency: str
    low_balance_threshold_microdollars: int
    spend_limit_microdollars: int | None = None
    monthly_spend_microdollars: int = 0


def _auth_response(result) -> AuthResponse:
    settings = get_settings()
    return AuthResponse(
        access_token=result.jwt_token,
        expires_in=settings.jwt_expiry_seconds,
        user=UserResponse(
            id=result.user.id,
            email=result.user.email,
            display_name=result.user.display_name,
        ),
    )


@router.post("/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    if get_user_by_email(db, body.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "email_taken", "message": "Email already registered"}},
        )

    user = create_user(db, body.email, body.password, display_name=body.display_name)
    get_or_create_wallet(db, user.id)
    result = issue_session(db, user)
    return _auth_response(result)


@router.post("/auth/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = authenticate_user(db, body.email, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {"code": "invalid_credentials", "message": "Invalid email or password"}
            },
        )

    result = issue_session(db, user)
    return _auth_response(result)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    user_session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> None:
    invalidate_session(db, user_session)


@router.get("/me", response_model=MeResponse)
def get_me(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeResponse:
    summary = get_wallet_summary_for_user(db, user.id)
    return MeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        wallet_id=summary.wallet_id,
        balance_microdollars=summary.balance_microdollars,
        held_microdollars=summary.held_microdollars,
        available_microdollars=summary.available_microdollars,
        currency=summary.currency,
        low_balance_threshold_microdollars=summary.low_balance_threshold_microdollars,
        spend_limit_microdollars=summary.spend_limit_microdollars,
        monthly_spend_microdollars=summary.monthly_spend_microdollars,
    )


class GoogleCallbackRequest(BaseModel):
    code: str = Field(min_length=1)
    state: str = Field(min_length=1)


@router.get("/auth/oauth/google")
def google_login(request: Request) -> RedirectResponse:
    try:
        raw_state = secrets.token_urlsafe(24)
        url = authorization_url(state=raw_state)
    except GoogleNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "google_not_configured", "message": str(exc)}},
        ) from exc

    response = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        _OAUTH_STATE_COOKIE,
        _sign_state(raw_state),
        max_age=_OAUTH_STATE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=get_settings().is_production,
    )
    return response


@router.post("/auth/oauth/google/callback", response_model=AuthResponse)
def google_callback(
    body: GoogleCallbackRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    signed = request.cookies.get(_OAUTH_STATE_COOKIE)
    if not signed or not _verify_state(body.state, signed):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_state", "message": "OAuth state mismatch"}},
        )

    try:
        profile = exchange_code_and_profile(body.code)
    except GoogleOAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "google_exchange_failed", "message": str(exc)}},
        ) from exc

    user = get_or_create_oauth_user(
        db,
        provider="google",
        provider_sub=profile.sub,
        email=profile.email,
        display_name=profile.name,
    )
    get_or_create_wallet(db, user.id)
    result = issue_session(db, user)
    response.delete_cookie(_OAUTH_STATE_COOKIE)
    return _auth_response(result)
