import asyncio

from fastapi import APIRouter, Response

from services.shared.config import get_settings
from services.shared.db import check_database
from services.shared.redis_client import check_redis

router = APIRouter(tags=["System"])


@router.get("/health")
async def health_check(response: Response) -> dict[str, str]:
    """Liveness/readiness probe: PostgreSQL and Redis connectivity."""
    settings = get_settings()

    db_status = "ok"
    redis_status = "ok"

    try:
        await asyncio.wait_for(check_database(settings.database_url_async), timeout=5)
    except Exception:
        db_status = "error"

    try:
        redis_ok = await asyncio.wait_for(check_redis(settings.redis_url), timeout=5)
        if not redis_ok:
            redis_status = "error"
    except Exception:
        redis_status = "error"

    healthy = db_status == "ok" and redis_status == "ok"
    response.status_code = 200 if healthy else 503

    return {
        "status": "ok" if healthy else "degraded",
        "database": db_status,
        "redis": redis_status,
    }
