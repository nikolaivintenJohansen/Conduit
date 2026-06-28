import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.shared.config import get_settings
from services.shared.models import AccessGroup, VirtualKey


class AccessGroupNotFoundError(ValueError):
    pass


KEY_PREFIX = "sk-uaw-"


@dataclass(frozen=True)
class GeneratedKey:
    plaintext: str
    prefix: str
    key_hash: str


def hash_key(plaintext: str, pepper: str | None = None) -> str:
    secret = (pepper or get_settings().key_hash_pepper).encode()
    return hmac.new(secret, plaintext.encode(), hashlib.sha256).hexdigest()


def generate_virtual_key() -> GeneratedKey:
    token = secrets.token_urlsafe(32)
    plaintext = f"{KEY_PREFIX}{token}"
    prefix = plaintext[:12]
    return GeneratedKey(plaintext=plaintext, prefix=prefix, key_hash=hash_key(plaintext))


def verify_key(plaintext: str, stored_hash: str, pepper: str | None = None) -> bool:
    candidate = hash_key(plaintext, pepper=pepper)
    return hmac.compare_digest(candidate, stored_hash)


def resolve_virtual_key(session: Session, bearer_token: str) -> VirtualKey | None:
    if not bearer_token.startswith(KEY_PREFIX):
        return None

    key_hash = hash_key(bearer_token)
    stmt = select(VirtualKey).where(
        VirtualKey.key_hash == key_hash,
        VirtualKey.revoked_at.is_(None),
    )
    return session.scalar(stmt)


@dataclass(frozen=True)
class CreatedVirtualKey:
    record: VirtualKey
    plaintext: str


def list_user_virtual_keys(session: Session, user_id: UUID) -> list[VirtualKey]:
    stmt = (
        select(VirtualKey)
        .where(VirtualKey.user_id == user_id)
        .order_by(VirtualKey.created_at.desc())
    )
    return list(session.scalars(stmt).all())


def get_user_virtual_key(session: Session, user_id: UUID, key_id: UUID) -> VirtualKey | None:
    return session.scalar(
        select(VirtualKey).where(
            VirtualKey.id == key_id,
            VirtualKey.user_id == user_id,
        )
    )


def create_user_virtual_key(
    session: Session,
    user_id: UUID,
    *,
    name: str | None = None,
    rpm_limit: int | None = None,
    tpm_limit: int | None = None,
    access_group_id: UUID | None = None,
    partner_account_id: UUID | None = None,
) -> CreatedVirtualKey:
    if access_group_id is not None and session.get(AccessGroup, access_group_id) is None:
        raise AccessGroupNotFoundError("Access group not found")

    settings = get_settings()
    generated = generate_virtual_key()
    record = VirtualKey(
        user_id=user_id,
        name=name,
        key_prefix=generated.prefix,
        key_hash=generated.key_hash,
        rpm_limit=rpm_limit if rpm_limit is not None else settings.default_rpm_limit,
        tpm_limit=tpm_limit if tpm_limit is not None else settings.default_tpm_limit,
        access_group_id=access_group_id,
        partner_account_id=partner_account_id,
    )
    session.add(record)
    session.flush()
    return CreatedVirtualKey(record=record, plaintext=generated.plaintext)


def revoke_virtual_key(session: Session, user_id: UUID, key_id: UUID) -> VirtualKey | None:
    record = get_user_virtual_key(session, user_id, key_id)
    if record is None:
        return None
    if record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)
        session.flush()
    return record


def assign_access_group_to_key(
    session: Session,
    user_id: UUID,
    key_id: UUID,
    access_group_id: UUID | None,
) -> VirtualKey | None:
    record = get_user_virtual_key(session, user_id, key_id)
    if record is None or record.revoked_at is not None:
        return None

    if access_group_id is not None and session.get(AccessGroup, access_group_id) is None:
        raise AccessGroupNotFoundError("Access group not found")

    record.access_group_id = access_group_id
    session.flush()
    return record


def rotate_virtual_key(session: Session, user_id: UUID, key_id: UUID) -> CreatedVirtualKey | None:
    record = get_user_virtual_key(session, user_id, key_id)
    if record is None or record.revoked_at is not None:
        return None

    record.revoked_at = datetime.now(UTC)
    return create_user_virtual_key(
        session,
        user_id,
        name=record.name,
        rpm_limit=record.rpm_limit,
        tpm_limit=record.tpm_limit,
        access_group_id=record.access_group_id,
        partner_account_id=record.partner_account_id,
    )
