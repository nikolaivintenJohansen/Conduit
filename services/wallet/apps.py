"""User-facing connected apps: consent, allowances, and revocation (Phase 3).

A user connects a partner app (an `app_registrations` client) which creates an
`app_installs` row carrying a per-app spend allowance. The gateway enforces the
allowance on the Redis fast path (see services/gateway/access.py); this module
owns the authoritative DB state and the cache-invalidation side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.shared.models import AppInstall, AppRegistration, OAuthRefreshToken


class AppNotFoundError(Exception):
    pass


class AppNotActiveError(Exception):
    pass


@dataclass(frozen=True)
class ConnectedApp:
    install: AppInstall
    registration: AppRegistration


def _load_registration(session: Session, client_id: str) -> AppRegistration:
    reg = session.scalar(select(AppRegistration).where(AppRegistration.client_id == client_id))
    if reg is None:
        raise AppNotFoundError(f"unknown client_id {client_id}")
    if not reg.is_active:
        raise AppNotActiveError(f"app {client_id} is not active")
    return reg


def list_connected_apps(session: Session, user_id: UUID) -> list[ConnectedApp]:
    stmt = (
        select(AppInstall, AppRegistration)
        .join(AppRegistration, AppInstall.app_registration_id == AppRegistration.id)
        .where(AppInstall.user_id == user_id)
        .order_by(AppInstall.consented_at.desc())
    )
    rows = list(session.execute(stmt).all())
    return [ConnectedApp(install=install, registration=reg) for install, reg in rows]


def get_install_for_user(session: Session, user_id: UUID, install_id: UUID) -> AppInstall | None:
    return session.scalar(
        select(AppInstall).where(
            AppInstall.id == install_id,
            AppInstall.user_id == user_id,
        )
    )


def connect_app(
    session: Session,
    *,
    user_id: UUID,
    client_id: str,
    spend_limit_microdollars: int | None = None,
    reset_period: str = "monthly",
    display_name: str | None = None,
) -> AppInstall:
    if reset_period not in ("monthly", "lifetime"):
        raise ValueError("reset_period must be 'monthly' or 'lifetime'")
    if spend_limit_microdollars is not None and spend_limit_microdollars < 0:
        raise ValueError("spend_limit_microdollars must be >= 0")

    reg = _load_registration(session, client_id)

    # Reactivate an existing (possibly revoked) install for the same app.
    existing = session.scalar(
        select(AppInstall).where(
            AppInstall.user_id == user_id,
            AppInstall.app_registration_id == reg.id,
        )
    )
    if existing is not None:
        existing.revoked_at = None
        existing.consented_at = datetime.now(UTC)
        existing.spend_limit_microdollars = spend_limit_microdollars
        existing.allowance_reset_period = reset_period
        existing.display_name = display_name
        session.flush()
        return existing

    install = AppInstall(
        user_id=user_id,
        app_registration_id=reg.id,
        spend_limit_microdollars=spend_limit_microdollars,
        allowance_reset_period=reset_period,
        display_name=display_name,
    )
    session.add(install)
    session.flush()
    return install


def update_allowance(
    session: Session,
    *,
    user_id: UUID,
    install_id: UUID,
    spend_limit_microdollars: int | None,
) -> AppInstall | None:
    install = get_install_for_user(session, user_id, install_id)
    if install is None or install.revoked_at is not None:
        return None
    if spend_limit_microdollars is not None and spend_limit_microdollars < 0:
        raise ValueError("spend_limit_microdollars must be >= 0")
    install.spend_limit_microdollars = spend_limit_microdollars
    session.flush()
    return install


def revoke_app(session: Session, *, user_id: UUID, install_id: UUID) -> AppInstall | None:
    install = get_install_for_user(session, user_id, install_id)
    if install is None:
        return None
    install.revoked_at = datetime.now(UTC)

    # Revoke all refresh tokens bound to this install.
    refresh_tokens = list(
        session.scalars(
            select(OAuthRefreshToken).where(
                OAuthRefreshToken.app_install_id == install.id,
                OAuthRefreshToken.revoked_at.is_(None),
            )
        ).all()
    )
    for token in refresh_tokens:
        token.revoked_at = datetime.now(UTC)

    session.flush()
    return install


def has_allowance_available(install: AppInstall, estimated_cost_microdollars: int) -> bool:
    if install.revoked_at is not None:
        return False
    if install.spend_limit_microdollars is None:
        return True
    return (
        install.allowance_spent_microdollars + estimated_cost_microdollars
        <= install.spend_limit_microdollars
    )
