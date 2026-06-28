from fastapi import Header, HTTPException, status

from services.shared.config import get_settings


def require_partner_admin(
    x_partner_admin_token: str | None = Header(default=None, alias="X-Partner-Admin-Token"),
) -> None:
    settings = get_settings()
    if not x_partner_admin_token or x_partner_admin_token != settings.partner_admin_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "unauthorized",
                    "message": "Valid X-Partner-Admin-Token header required",
                }
            },
        )
