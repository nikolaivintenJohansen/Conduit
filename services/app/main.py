from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.app.dashboard.routes import router as dashboard_router
from services.app.gateway.authorize_routes import router as authorize_router
from services.app.gateway.middleware import GatewayResponseHeadersMiddleware
from services.app.gateway.routes import router as gateway_router
from services.app.pricing.routes import router as pricing_router
from services.app.routes.health import router as health_router
from services.app.wallet.access_groups_routes import router as access_groups_router
from services.app.wallet.app_registrations_routes import router as app_registrations_router
from services.app.wallet.apps_routes import router as apps_router
from services.app.wallet.auth_routes import router as auth_router
from services.app.wallet.keys_routes import router as keys_router
from services.app.wallet.oauth_routes import router as oauth_router
from services.app.wallet.routes import router as wallet_router
from services.app.wallet.settlement_routes import router as settlement_router
from services.app.wallet.topups_routes import router as topups_router
from services.app.wallet.usage_routes import router as usage_router
from services.gateway import worker as billing_worker
from services.shared.config import get_settings
from services.shared.logging import configure_logging
from services.shared.middleware import RequestLoggingMiddleware
from services.wallet import settlement_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level, settings.app_env)
    worker_task = None
    if settings.worker_enabled:
        import asyncio

        async def _run_worker():
            await asyncio.to_thread(billing_worker.run_loop)

        worker_task = asyncio.create_task(_run_worker())
    settlement_task = settlement_scheduler.start_scheduler()
    yield
    if worker_task is not None:
        worker_task.cancel()
    if settlement_task is not None:
        settlement_task.cancel()


app = FastAPI(title="Universal AI Wallet", version="0.1.0", lifespan=lifespan)
app.add_middleware(GatewayResponseHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(access_groups_router)
app.include_router(app_registrations_router)
app.include_router(apps_router)
app.include_router(keys_router)
app.include_router(wallet_router)
app.include_router(topups_router)
app.include_router(usage_router)
app.include_router(oauth_router)
app.include_router(pricing_router)
app.include_router(settlement_router)
app.include_router(dashboard_router)
app.include_router(gateway_router)
app.include_router(authorize_router)
