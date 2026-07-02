import asyncio
import logging
import re

from fastapi import APIRouter, Response

from services.shared.config import get_settings
from services.shared.db import check_database
from services.shared.redis_client import check_redis

router = APIRouter(tags=["System"])
logger = logging.getLogger("conduit.health")


def _safe_error(exc: Exception) -> str:
    message = f"{type(exc).__name__}: {exc}"
    return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:***@", message)


@router.get("/health")
async def health_check(response: Response) -> dict[str, str]:
    """Liveness/readiness probe: PostgreSQL and Redis connectivity."""
    settings = get_settings()

    db_status = "ok"
    redis_status = "ok"

    try:
        await asyncio.wait_for(check_database(settings.database_url_async), timeout=5)
    except Exception as exc:
        db_status = "error"
        logger.warning("database health check failed: %s", _safe_error(exc))

    try:
        redis_ok = await asyncio.wait_for(check_redis(settings.redis_url), timeout=5)
        if not redis_ok:
            redis_status = "error"
    except Exception as exc:
        redis_status = "error"
        logger.warning("redis health check failed: %s", _safe_error(exc))

    healthy = db_status == "ok" and redis_status == "ok"
    response.status_code = 200 if healthy else 503
    if not healthy:
        logger.warning("health check degraded: database=%s redis=%s", db_status, redis_status)

    return {
        "status": "ok" if healthy else "degraded",
        "database": db_status,
        "redis": redis_status,
    }
