"""Partner app registration CRUD (Phase 3).

Partner admins register OAuth clients here. `client_secret` is shown once at
creation/rotation and stored only as an HMAC hash (reusing the key pepper).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.shared.models import AppRegistration
from services.wallet.keys import hash_key

CLIENT_ID_PREFIX = "conduit_"
DEFAULT_SCOPES = ["wallet:charge", "profile:read"]


@dataclass(frozen=True)
class CreatedAppRegistration:
    record: AppRegistration
    client_secret: str


def _generate_client_id() -> str:
    return f"{CLIENT_ID_PREFIX}{secrets.token_urlsafe(18)}"


def _generate_client_secret() -> str:
    return secrets.token_urlsafe(32)


def get_app_registration_by_client_id(session: Session, client_id: str) -> AppRegistration | None:
    return session.scalar(select(AppRegistration).where(AppRegistration.client_id == client_id))


def get_app_registration(session: Session, registration_id: UUID) -> AppRegistration | None:
    return session.get(AppRegistration, registration_id)


def list_app_registrations(
    session: Session, partner_account_id: UUID | None = None
) -> list[AppRegistration]:
    stmt = select(AppRegistration).order_by(AppRegistration.created_at.desc())
    if partner_account_id is not None:
        stmt = stmt.where(AppRegistration.partner_account_id == partner_account_id)
    return list(session.scalars(stmt).all())


def create_app_registration(
    session: Session,
    *,
    partner_account_id: UUID,
    name: str,
    redirect_uris: list[str],
    scopes: list[str] | None = None,
    logo_url: str | None = None,
) -> CreatedAppRegistration:
    if not redirect_uris:
        raise ValueError("at least one redirect_uri is required")

    plaintext_secret = _generate_client_secret()
    record = AppRegistration(
        partner_account_id=partner_account_id,
        name=name,
        client_id=_generate_client_id(),
        client_secret_hash=hash_key(plaintext_secret),
        redirect_uris=redirect_uris,
        scopes=scopes or list(DEFAULT_SCOPES),
        is_active=True,
        logo_url=logo_url,
    )
    session.add(record)
    session.flush()
    return CreatedAppRegistration(record=record, client_secret=plaintext_secret)


def update_app_registration(
    session: Session,
    registration_id: UUID,
    *,
    name: str | None = None,
    redirect_uris: list[str] | None = None,
    scopes: list[str] | None = None,
    logo_url: str | None = None,
    is_active: bool | None = None,
) -> AppRegistration | None:
    record = get_app_registration(session, registration_id)
    if record is None:
        return None
    if redirect_uris is not None and not redirect_uris:
        raise ValueError("at least one redirect_uri is required")
    if name is not None:
        record.name = name
    if redirect_uris is not None:
        record.redirect_uris = redirect_uris
    if scopes is not None:
        record.scopes = scopes
    if logo_url is not None:
        record.logo_url = logo_url
    if is_active is not None:
        record.is_active = is_active
    session.flush()
    return record


def rotate_client_secret(session: Session, registration_id: UUID) -> CreatedAppRegistration | None:
    record = get_app_registration(session, registration_id)
    if record is None:
        return None
    plaintext_secret = _generate_client_secret()
    record.client_secret_hash = hash_key(plaintext_secret)
    session.flush()
    return CreatedAppRegistration(record=record, client_secret=plaintext_secret)


def deactivate_app_registration(session: Session, registration_id: UUID) -> bool:
    record = get_app_registration(session, registration_id)
    if record is None:
        return False
    record.is_active = False
    session.flush()
    return True


def verify_client_secret(record: AppRegistration, plaintext_secret: str) -> bool:
    from services.wallet.keys import verify_key

    return verify_key(plaintext_secret, record.client_secret_hash)
