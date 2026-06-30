from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from services.shared.config import get_settings
from services.shared.models import AppRegistration, VirtualKey
from services.wallet.deps import get_db
from services.wallet.keys import KEY_PREFIX, resolve_virtual_key
from services.wallet.oauth import (
    InvalidTokenError,
    decode_access_token,
    get_install_for_access_token,
)

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class GatewayCaller:
    """Unified gateway auth context for either a virtual key or an app access token."""

    user_id: UUID
    virtual_key_id: UUID | None
    access_group_id: UUID | None
    partner_account_id: UUID | None
    rpm_limit: int
    tpm_limit: int
    budget_microdollars: int | None
    app_install_id: UUID | None
    scopes: list[str]

    @property
    def is_app_scoped(self) -> bool:
        return self.app_install_id is not None

    @property
    def rate_limit_key(self) -> UUID:
        return self.virtual_key_id or self.app_install_id  # type: ignore[return-value]


def get_virtual_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> VirtualKey:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "invalid_api_key",
                    "message": "Bearer virtual API key required",
                }
            },
        )

    token = credentials.credentials
    if not token.startswith(KEY_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "invalid_api_key",
                    "message": "Invalid API key format",
                }
            },
        )

    virtual_key = resolve_virtual_key(db, token)
    if virtual_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "invalid_api_key",
                    "message": "Unknown or revoked API key",
                }
            },
        )

    return virtual_key


def get_gateway_caller(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> GatewayCaller:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "invalid_api_key", "message": "Bearer token required"}},
        )

    token = credentials.credentials

    # Path 1: virtual key (sk-conduit-*).
    if token.startswith(KEY_PREFIX):
        virtual_key = resolve_virtual_key(db, token)
        if virtual_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": {"code": "invalid_api_key", "message": "Unknown or revoked API key"}
                },
            )
        return GatewayCaller(
            user_id=virtual_key.user_id,
            virtual_key_id=virtual_key.id,
            access_group_id=virtual_key.access_group_id,
            partner_account_id=virtual_key.partner_account_id,
            rpm_limit=virtual_key.rpm_limit,
            tpm_limit=virtual_key.tpm_limit,
            budget_microdollars=virtual_key.budget_microdollars,
            app_install_id=None,
            scopes=[],
        )

    # Path 2: OAuth app access token (JWT with app_install_id).
    try:
        payload = decode_access_token(token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "invalid_api_key", "message": str(exc)}},
        ) from exc

    install = get_install_for_access_token(db, payload)
    if install is None or install.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {"code": "app_revoked", "message": "App access revoked or not connected"}
            },
        )

    reg = db.get(AppRegistration, install.app_registration_id)
    partner_account_id = reg.partner_account_id if reg is not None else None
    settings = get_settings()
    scopes = str(payload.get("scope", "")).split()

    return GatewayCaller(
        user_id=install.user_id,
        virtual_key_id=None,
        access_group_id=None,  # app-scoped calls allow all models in MVP
        partner_account_id=partner_account_id,
        rpm_limit=settings.default_rpm_limit,
        tpm_limit=settings.default_tpm_limit,
        budget_microdollars=None,
        app_install_id=install.id,
        scopes=scopes,
    )
