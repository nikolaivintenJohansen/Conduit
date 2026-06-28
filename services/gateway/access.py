from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.gateway import allowance_cache
from services.shared.models import AccessGroupModel, ModelCatalog, VirtualKey


class AccessDeniedError(Exception):
    pass


class AllowanceExceededError(Exception):
    pass


class AppRevokedError(Exception):
    pass


def is_model_allowed(session: Session, access_group_id: UUID | None, model_slug: str) -> bool:
    """Return True when no group is set (allow-all) or model is in the group."""
    if access_group_id is None:
        return True

    stmt = (
        select(ModelCatalog.id)
        .join(AccessGroupModel, AccessGroupModel.model_id == ModelCatalog.id)
        .where(
            AccessGroupModel.access_group_id == access_group_id,
            ModelCatalog.slug == model_slug,
            ModelCatalog.is_active.is_(True),
        )
    )
    return session.scalar(stmt) is not None


def enforce_model_access(session: Session, virtual_key: VirtualKey, model_slug: str) -> None:
    if not is_model_allowed(session, virtual_key.access_group_id, model_slug):
        raise AccessDeniedError(f"model {model_slug} not allowed for this key")


def enforce_model_access_for_group(
    session: Session, access_group_id: UUID | None, model_slug: str
) -> None:
    if not is_model_allowed(session, access_group_id, model_slug):
        raise AccessDeniedError(f"model {model_slug} not allowed for this caller")


def enforce_app_allowance(
    session: Session, app_install_id: UUID, estimated_cost_microdollars: int
) -> None:
    """Fast-path per-app spend check. Reads from Redis; falls back to DB on cache miss."""
    state = allowance_cache.get_allowance_state(app_install_id)
    if state is None:
        state = allowance_cache.load_state_from_db(session, app_install_id)
    if state is None:
        raise AppRevokedError("app install not found")
    if state["revoked"]:
        raise AppRevokedError("app access revoked")
    limit = state["spend_limit_microdollars"]
    if (
        limit is not None
        and state["allowance_spent_microdollars"] + estimated_cost_microdollars > limit
    ):
        raise AllowanceExceededError(
            f"app allowance {limit} exceeded (spent {state['allowance_spent_microdollars']}, "
            f"needed +{estimated_cost_microdollars})"
        )
