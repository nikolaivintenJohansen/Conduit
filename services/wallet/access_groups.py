from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from services.shared.models import AccessGroup, AccessGroupModel, ModelCatalog


class UnknownModelSlugError(ValueError):
    pass


@dataclass(frozen=True)
class AccessGroupDetail:
    group: AccessGroup
    model_slugs: list[str]


def _get_model_slugs_for_group(session: Session, group_id: UUID) -> list[str]:
    stmt = (
        select(ModelCatalog.slug)
        .join(AccessGroupModel, AccessGroupModel.model_id == ModelCatalog.id)
        .where(AccessGroupModel.access_group_id == group_id)
        .order_by(ModelCatalog.slug)
    )
    return list(session.scalars(stmt).all())


def _resolve_model_ids(session: Session, model_slugs: list[str]) -> list[UUID]:
    if not model_slugs:
        return []

    stmt = select(ModelCatalog).where(
        ModelCatalog.slug.in_(model_slugs),
        ModelCatalog.is_active.is_(True),
    )
    models = list(session.scalars(stmt).all())
    found = {model.slug for model in models}
    missing = set(model_slugs) - found
    if missing:
        raise UnknownModelSlugError(f"Unknown or inactive models: {', '.join(sorted(missing))}")

    slug_to_id = {model.slug: model.id for model in models}
    return [slug_to_id[slug] for slug in model_slugs]


def _set_group_models(session: Session, group_id: UUID, model_ids: list[UUID]) -> None:
    session.execute(delete(AccessGroupModel).where(AccessGroupModel.access_group_id == group_id))
    for model_id in model_ids:
        session.add(AccessGroupModel(access_group_id=group_id, model_id=model_id))
    session.flush()


def _to_detail(session: Session, group: AccessGroup) -> AccessGroupDetail:
    return AccessGroupDetail(group=group, model_slugs=_get_model_slugs_for_group(session, group.id))


def list_access_groups(session: Session) -> list[AccessGroupDetail]:
    groups = list(session.scalars(select(AccessGroup).order_by(AccessGroup.name)).all())
    return [_to_detail(session, group) for group in groups]


def get_access_group(session: Session, group_id: UUID) -> AccessGroupDetail | None:
    group = session.get(AccessGroup, group_id)
    if group is None:
        return None
    return _to_detail(session, group)


def create_access_group(
    session: Session,
    *,
    name: str,
    description: str | None = None,
    model_slugs: list[str] | None = None,
) -> AccessGroupDetail:
    group = AccessGroup(name=name, description=description)
    session.add(group)
    session.flush()

    slugs = model_slugs or []
    model_ids = _resolve_model_ids(session, slugs)
    _set_group_models(session, group.id, model_ids)
    return _to_detail(session, group)


def update_access_group(
    session: Session,
    group_id: UUID,
    *,
    name: str | None = None,
    description: str | None = None,
    model_slugs: list[str] | None = None,
) -> AccessGroupDetail | None:
    group = session.get(AccessGroup, group_id)
    if group is None:
        return None

    if name is not None:
        group.name = name
    if description is not None:
        group.description = description
    if model_slugs is not None:
        model_ids = _resolve_model_ids(session, model_slugs)
        _set_group_models(session, group.id, model_ids)

    session.flush()
    return _to_detail(session, group)


def delete_access_group(session: Session, group_id: UUID) -> bool:
    group = session.get(AccessGroup, group_id)
    if group is None:
        return False
    session.delete(group)
    session.flush()
    return True


def list_catalog_models(session: Session) -> list[ModelCatalog]:
    stmt = select(ModelCatalog).where(ModelCatalog.is_active.is_(True)).order_by(ModelCatalog.slug)
    return list(session.scalars(stmt).all())
