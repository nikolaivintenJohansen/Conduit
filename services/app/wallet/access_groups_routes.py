from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from services.shared.models import User
from services.wallet.access_groups import (
    UnknownModelSlugError,
    create_access_group,
    delete_access_group,
    get_access_group,
    list_access_groups,
    list_catalog_models,
    update_access_group,
)
from services.wallet.deps import get_current_user, get_db

router = APIRouter(prefix="/wallet/v1", tags=["Access Groups"])


class ModelCatalogResponse(BaseModel):
    id: UUID
    slug: str
    display_name: str
    provider: str


class ModelCatalogListResponse(BaseModel):
    data: list[ModelCatalogResponse]


class AccessGroupResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    model_slugs: list[str]
    created_at: datetime


class AccessGroupListResponse(BaseModel):
    data: list[AccessGroupResponse]


class CreateAccessGroupRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    model_slugs: list[str] = Field(default_factory=list)


class UpdateAccessGroupRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    model_slugs: list[str] | None = None


def _group_response(detail) -> AccessGroupResponse:
    return AccessGroupResponse(
        id=detail.group.id,
        name=detail.group.name,
        description=detail.group.description,
        model_slugs=detail.model_slugs,
        created_at=detail.group.created_at,
    )


def _model_not_found_error(exc: UnknownModelSlugError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"error": {"code": "invalid_model_slug", "message": str(exc)}},
    )


@router.get("/models", response_model=ModelCatalogListResponse)
def list_models(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ModelCatalogListResponse:
    models = list_catalog_models(db)
    return ModelCatalogListResponse(
        data=[
            ModelCatalogResponse(
                id=model.id,
                slug=model.slug,
                display_name=model.display_name,
                provider=model.provider,
            )
            for model in models
        ]
    )


@router.get("/access-groups", response_model=AccessGroupListResponse)
def list_groups(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccessGroupListResponse:
    groups = list_access_groups(db)
    return AccessGroupListResponse(data=[_group_response(group) for group in groups])


@router.post(
    "/access-groups",
    response_model=AccessGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_group(
    body: CreateAccessGroupRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccessGroupResponse:
    try:
        created = create_access_group(
            db,
            name=body.name,
            description=body.description,
            model_slugs=body.model_slugs,
        )
    except UnknownModelSlugError as exc:
        raise _model_not_found_error(exc) from exc
    return _group_response(created)


@router.get("/access-groups/{group_id}", response_model=AccessGroupResponse)
def get_group(
    group_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccessGroupResponse:
    detail = get_access_group(db, group_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {"code": "access_group_not_found", "message": "Access group not found"}
            },
        )
    return _group_response(detail)


@router.patch("/access-groups/{group_id}", response_model=AccessGroupResponse)
def update_group(
    group_id: UUID,
    body: UpdateAccessGroupRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccessGroupResponse:
    try:
        updated = update_access_group(
            db,
            group_id,
            name=body.name,
            description=body.description,
            model_slugs=body.model_slugs,
        )
    except UnknownModelSlugError as exc:
        raise _model_not_found_error(exc) from exc

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {"code": "access_group_not_found", "message": "Access group not found"}
            },
        )
    return _group_response(updated)


@router.delete("/access-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not delete_access_group(db, group_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {"code": "access_group_not_found", "message": "Access group not found"}
            },
        )
