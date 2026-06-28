import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("uaw.http")


def _auth_context(authorization: str | None) -> tuple[str, str | None]:
    if not authorization:
        return "none", None

    if authorization.startswith("Bearer sk-uaw-"):
        token = authorization.removeprefix("Bearer ").strip()
        prefix = token[:12] if len(token) >= 12 else token
        return "virtual_key", prefix

    if authorization.startswith("Bearer "):
        return "jwt", None

    return "unknown", None


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Structured request logging: auth hint, route, latency, optional cost header."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id

        auth_type, key_prefix = _auth_context(request.headers.get("Authorization"))
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "latency_ms": latency_ms,
                    "auth_type": auth_type,
                    "key_prefix": key_prefix,
                }
            )
            raise

        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)

        response.headers["X-Request-Id"] = request_id

        logger.info(
            {
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "route": route_path,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
                "auth_type": auth_type,
                "key_prefix": key_prefix,
                "cost_usd": response.headers.get("X-UAW-Cost-USD"),
            }
        )

        return response
