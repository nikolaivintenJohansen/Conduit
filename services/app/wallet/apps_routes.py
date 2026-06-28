from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from services.gateway import allowance_cache
from services.shared.models import AppInstall, User
from services.wallet.apps import (
    AppNotActiveError,
    AppNotFoundError,
    connect_app,
    get_install_for_user,
    list_connected_apps,
    revoke_app,
    update_allowance,
)
from services.wallet.deps import get_current_user, get_db

router = APIRouter(prefix="/wallet/v1/apps", tags=["Connected Apps"])


class ConnectedAppResponse(BaseModel):
    install_id: UUID
    client_id: str
    app_name: str
    display_name: str | None
    spend_limit_microdollars: int | None
    allowance_spent_microdollars: int
    allowance_reset_period: str
    consented_at: datetime
    revoked_at: datetime | None


class ConnectedAppListResponse(BaseModel):
    data: list[ConnectedAppResponse]


class ConnectAppRequest(BaseModel):
    spend_limit_microdollars: int | None = Field(default=None, ge=0)
    reset_period: str = Field(default="monthly")
    display_name: str | None = None


class UpdateAllowanceRequest(BaseModel):
    spend_limit_microdollars: int | None = Field(default=None, ge=0)


def _install_response(install: AppInstall, app_name: str, client_id: str) -> ConnectedAppResponse:
    return ConnectedAppResponse(
        install_id=install.id,
        client_id=client_id,
        app_name=app_name,
        display_name=install.display_name,
        spend_limit_microdollars=install.spend_limit_microdollars,
        allowance_spent_microdollars=install.allowance_spent_microdollars,
        allowance_reset_period=install.allowance_reset_period,
        consented_at=install.consented_at,
        revoked_at=install.revoked_at,
    )


def _sync_allowance_cache(install: AppInstall) -> None:
    """Keep the Redis fast-path projection in sync with the authoritative DB row."""
    allowance_cache.set_allowance_state(
        install.id,
        spend_limit_microdollars=install.spend_limit_microdollars,
        allowance_spent_microdollars=install.allowance_spent_microdollars,
        revoked=install.revoked_at is not None,
    )


@router.get("", response_model=ConnectedAppListResponse)
def list_apps(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectedAppListResponse:
    connected = list_connected_apps(db, user.id)
    return ConnectedAppListResponse(
        data=[
            _install_response(c.install, c.registration.name, c.registration.client_id)
            for c in connected
        ]
    )


@router.post(
    "/{client_id}/connect", response_model=ConnectedAppResponse, status_code=status.HTTP_201_CREATED
)
def connect(
    client_id: str,
    body: ConnectAppRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectedAppResponse:
    try:
        install = connect_app(
            db,
            user_id=user.id,
            client_id=client_id,
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

    reg = install.app_registration
    _sync_allowance_cache(install)
    return _install_response(install, reg.name, reg.client_id)


@router.patch("/{install_id}", response_model=ConnectedAppResponse)
def update_app_allowance(
    install_id: UUID,
    body: UpdateAllowanceRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectedAppResponse:
    try:
        install = update_allowance(
            db,
            user_id=user.id,
            install_id=install_id,
            spend_limit_microdollars=body.spend_limit_microdollars,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_allowance", "message": str(exc)}},
        ) from exc
    if install is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "install_not_found", "message": "Connected app not found"}},
        )
    reg = install.app_registration
    _sync_allowance_cache(install)
    return _install_response(install, reg.name, reg.client_id)


@router.delete("/{install_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke(
    install_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    install = revoke_app(db, user_id=user.id, install_id=install_id)
    if install is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "install_not_found", "message": "Connected app not found"}},
        )
    # Mark revoked in the fast path immediately so the gateway blocks without a DB read.
    allowance_cache.set_allowance_state(
        install.id,
        spend_limit_microdollars=install.spend_limit_microdollars,
        allowance_spent_microdollars=install.allowance_spent_microdollars,
        revoked=True,
    )


@router.get("/{install_id}", response_model=ConnectedAppResponse)
def get_app(
    install_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectedAppResponse:
    install = get_install_for_user(db, user.id, install_id)
    if install is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "install_not_found", "message": "Connected app not found"}},
        )
    reg = install.app_registration
    return _install_response(install, reg.name, reg.client_id)
