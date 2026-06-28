from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from services.shared.models import User, VirtualKey
from services.wallet.deps import get_current_user, get_db
from services.wallet.keys import (
    AccessGroupNotFoundError,
    assign_access_group_to_key,
    create_user_virtual_key,
    list_user_virtual_keys,
    revoke_virtual_key,
    rotate_virtual_key,
)

router = APIRouter(prefix="/wallet/v1", tags=["Keys"])


class CreateKeyRequest(BaseModel):
    name: str | None = None
    rpm_limit: int = Field(default=60, ge=0)
    tpm_limit: int = Field(default=100_000, ge=0)
    access_group_id: UUID | None = None


class UpdateKeyRequest(BaseModel):
    access_group_id: UUID | None = None


class VirtualKeyResponse(BaseModel):
    id: UUID
    name: str | None
    key_prefix: str
    rpm_limit: int
    tpm_limit: int
    access_group_id: UUID | None = None
    created_at: datetime
    revoked_at: datetime | None = None


class VirtualKeyCreatedResponse(VirtualKeyResponse):
    key: str


class VirtualKeyListResponse(BaseModel):
    data: list[VirtualKeyResponse]


def _key_response(record: VirtualKey) -> VirtualKeyResponse:
    return VirtualKeyResponse(
        id=record.id,
        name=record.name,
        key_prefix=record.key_prefix,
        rpm_limit=record.rpm_limit,
        tpm_limit=record.tpm_limit,
        access_group_id=record.access_group_id,
        created_at=record.created_at,
        revoked_at=record.revoked_at,
    )


@router.get("/keys", response_model=VirtualKeyListResponse)
def list_keys(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VirtualKeyListResponse:
    keys = list_user_virtual_keys(db, user.id)
    return VirtualKeyListResponse(data=[_key_response(key) for key in keys])


@router.post("/keys", response_model=VirtualKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_key(
    body: CreateKeyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VirtualKeyCreatedResponse:
    try:
        created = create_user_virtual_key(
            db,
            user.id,
            name=body.name,
            rpm_limit=body.rpm_limit,
            tpm_limit=body.tpm_limit,
            access_group_id=body.access_group_id,
        )
    except AccessGroupNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "access_group_not_found", "message": str(exc)}},
        ) from exc
    response = _key_response(created.record)
    return VirtualKeyCreatedResponse(**response.model_dump(), key=created.plaintext)


@router.post(
    "/keys/{key_id}/rotate",
    response_model=VirtualKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def rotate_key(
    key_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VirtualKeyCreatedResponse:
    rotated = rotate_virtual_key(db, user.id, key_id)
    if rotated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "key_not_found", "message": "Virtual key not found"}},
        )

    response = _key_response(rotated.record)
    return VirtualKeyCreatedResponse(**response.model_dump(), key=rotated.plaintext)


@router.patch("/keys/{key_id}", response_model=VirtualKeyResponse)
def update_key(
    key_id: UUID,
    body: UpdateKeyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VirtualKeyResponse:
    try:
        record = assign_access_group_to_key(
            db,
            user.id,
            key_id,
            body.access_group_id,
        )
    except AccessGroupNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "access_group_not_found", "message": str(exc)}},
        ) from exc

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "key_not_found", "message": "Virtual key not found"}},
        )
    return _key_response(record)


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_key(
    key_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    record = revoke_virtual_key(db, user.id, key_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "key_not_found", "message": "Virtual key not found"}},
        )
