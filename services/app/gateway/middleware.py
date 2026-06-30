from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class GatewayResponseHeadersMiddleware(BaseHTTPMiddleware):
    """Attach gateway billing headers after route handlers run."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        cost = getattr(request.state, "gateway_cost_microdollars", None)
        balance = getattr(request.state, "gateway_balance_microdollars", None)
        if cost is not None:
            response.headers["X-Conduit-Cost-USD"] = f"{cost / 1_000_000:.6f}"
        if balance is not None:
            response.headers["X-Conduit-Balance-Remaining-USD"] = f"{balance / 1_000_000:.6f}"
        return response
