from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from services.pricing.deps import require_partner_admin
from services.pricing.rules import get_partner_by_slug
from services.shared.config import get_settings
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
from services.wallet.partner_connect import (
    ConnectStatus,
    OnboardingResult,
    begin_onboarding,
    get_connect_status,
)

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


# ---------------------------------------------------------------------------
# Stripe Connect onboarding (Phase 7.1)
# ---------------------------------------------------------------------------


class ConnectOnboardRequest(BaseModel):
    return_url: str = Field(min_length=1)
    refresh_url: str = Field(min_length=1)


class ConnectOnboardResponse(BaseModel):
    partner_account_id: UUID
    partner_slug: str
    stripe_connect_id: str
    onboarding_url: str


class ConnectStatusResponse(BaseModel):
    partner_account_id: UUID
    partner_slug: str
    stripe_connect_id: str | None
    charges_enabled: bool
    details_submitted: bool
    payouts_enabled: bool
    capabilities: dict


def _connect_onboard_response(result: OnboardingResult) -> ConnectOnboardResponse:
    return ConnectOnboardResponse(
        partner_account_id=result.partner.id,
        partner_slug=result.partner.slug,
        stripe_connect_id=result.stripe_connect_id,
        onboarding_url=result.onboarding_url,
    )


def _connect_status_response(status: ConnectStatus) -> ConnectStatusResponse:
    return ConnectStatusResponse(
        partner_account_id=status.partner.id,
        partner_slug=status.partner.slug,
        stripe_connect_id=status.stripe_connect_id,
        charges_enabled=status.charges_enabled,
        details_submitted=status.details_submitted,
        payouts_enabled=status.payouts_enabled,
        capabilities=status.capabilities,
    )


@router.post(
    "/{partner_slug}/connect/onboard",
    response_model=ConnectOnboardResponse,
    status_code=status.HTTP_200_OK,
)
def connect_onboard(
    partner_slug: str,
    body: ConnectOnboardRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_partner_admin),
) -> ConnectOnboardResponse:
    partner = _require_partner(db, partner_slug)
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "stripe_not_configured", "message": "Stripe is not configured"}},
        )
    try:
        result = begin_onboarding(
            db, partner, return_url=body.return_url, refresh_url=body.refresh_url
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "stripe_onboarding_failed", "message": str(exc)}},
        ) from exc
    return _connect_onboard_response(result)


@router.get(
    "/{partner_slug}/connect/status",
    response_model=ConnectStatusResponse,
)
def connect_status(
    partner_slug: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_partner_admin),
) -> ConnectStatusResponse:
    partner = _require_partner(db, partner_slug)
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "stripe_not_configured", "message": "Stripe is not configured"}},
        )
    try:
        connect_status_result = get_connect_status(db, partner)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "stripe_status_failed", "message": str(exc)}},
        ) from exc
    return _connect_status_response(connect_status_result)
