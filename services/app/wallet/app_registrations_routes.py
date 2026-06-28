from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from services.pricing.deps import require_partner_admin
from services.pricing.rules import get_partner_by_slug
from services.shared.models import AppRegistration
from services.wallet.app_registrations import (
    CreatedAppRegistration,
    create_app_registration,
    deactivate_app_registration,
    get_app_registration,
    list_app_registrations,
    rotate_client_secret,
    update_app_registration,
)
from services.wallet.deps import get_db

router = APIRouter(prefix="/wallet/v1/partner", tags=["Partner Apps"])


class AppRegistrationResponse(BaseModel):
    id: UUID
    partner_account_id: UUID
    name: str
    client_id: str
    redirect_uris: list[str]
    scopes: list[str]
    is_active: bool
    logo_url: str | None
    created_at: datetime


class AppRegistrationCreatedResponse(AppRegistrationResponse):
    client_secret: str


class AppRegistrationListResponse(BaseModel):
    data: list[AppRegistrationResponse]


class CreateAppRegistrationRequest(BaseModel):
    name: str = Field(min_length=1)
    redirect_uris: list[str] = Field(min_length=1)
    scopes: list[str] | None = None
    logo_url: str | None = None


class UpdateAppRegistrationRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    redirect_uris: list[str] | None = None
    scopes: list[str] | None = None
    logo_url: str | None = None
    is_active: bool | None = None


def _require_partner(session: Session, partner_slug: str):
    partner = get_partner_by_slug(session, partner_slug)
    if partner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "partner_not_found", "message": "Partner not found"}},
        )
    return partner


def _response(record: AppRegistration) -> AppRegistrationResponse:
    return AppRegistrationResponse(
        id=record.id,
        partner_account_id=record.partner_account_id,
        name=record.name,
        client_id=record.client_id,
        redirect_uris=record.redirect_uris,
        scopes=record.scopes,
        is_active=record.is_active,
        logo_url=record.logo_url,
        created_at=record.created_at,
    )


def _created_response(created: CreatedAppRegistration) -> AppRegistrationCreatedResponse:
    base = _response(created.record)
    return AppRegistrationCreatedResponse(**base.model_dump(), client_secret=created.client_secret)


@router.post(
    "/{partner_slug}/apps",
    response_model=AppRegistrationCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_app(
    partner_slug: str,
    body: CreateAppRegistrationRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_partner_admin),
) -> AppRegistrationCreatedResponse:
    partner = _require_partner(db, partner_slug)
    try:
        created = create_app_registration(
            db,
            partner_account_id=partner.id,
            name=body.name,
            redirect_uris=body.redirect_uris,
            scopes=body.scopes,
            logo_url=body.logo_url,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_app_registration", "message": str(exc)}},
        ) from exc
    return _created_response(created)


@router.get("/{partner_slug}/apps", response_model=AppRegistrationListResponse)
def list_apps(
    partner_slug: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_partner_admin),
) -> AppRegistrationListResponse:
    partner = _require_partner(db, partner_slug)
    records = list_app_registrations(db, partner_account_id=partner.id)
    return AppRegistrationListResponse(data=[_response(r) for r in records])


@router.get("/{partner_slug}/apps/{registration_id}", response_model=AppRegistrationResponse)
def get_app(
    partner_slug: str,
    registration_id: UUID,
    db: Session = Depends(get_db),
    _: None = Depends(require_partner_admin),
) -> AppRegistrationResponse:
    _require_partner(db, partner_slug)
    record = get_app_registration(db, registration_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "app_not_found", "message": "App registration not found"}},
        )
    return _response(record)


@router.patch("/{partner_slug}/apps/{registration_id}", response_model=AppRegistrationResponse)
def update_app(
    partner_slug: str,
    registration_id: UUID,
    body: UpdateAppRegistrationRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_partner_admin),
) -> AppRegistrationResponse:
    _require_partner(db, partner_slug)
    try:
        record = update_app_registration(
            db,
            registration_id,
            name=body.name,
            redirect_uris=body.redirect_uris,
            scopes=body.scopes,
            logo_url=body.logo_url,
            is_active=body.is_active,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_app_registration", "message": str(exc)}},
        ) from exc
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "app_not_found", "message": "App registration not found"}},
        )
    return _response(record)


@router.post(
    "/{partner_slug}/apps/{registration_id}/rotate-secret",
    response_model=AppRegistrationCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def rotate_secret(
    partner_slug: str,
    registration_id: UUID,
    db: Session = Depends(get_db),
    _: None = Depends(require_partner_admin),
) -> AppRegistrationCreatedResponse:
    _require_partner(db, partner_slug)
    created = rotate_client_secret(db, registration_id)
    if created is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "app_not_found", "message": "App registration not found"}},
        )
    return _created_response(created)


@router.delete("/{partner_slug}/apps/{registration_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_app(
    partner_slug: str,
    registration_id: UUID,
    db: Session = Depends(get_db),
    _: None = Depends(require_partner_admin),
) -> None:
    _require_partner(db, partner_slug)
    if not deactivate_app_registration(db, registration_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "app_not_found", "message": "App registration not found"}},
        )
