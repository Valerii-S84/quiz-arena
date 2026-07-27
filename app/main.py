import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes.admin import router as admin_router
from app.api.routes.health import router as health_router
from app.api.routes.internal_analytics import router as internal_analytics_router
from app.api.routes.internal_offers import router as internal_offers_router
from app.api.routes.internal_promo import router as internal_promo_router
from app.api.routes.internal_referrals import router as internal_referrals_router
from app.api.routes.ops_ui import OPS_UI_STATIC_DIR
from app.api.routes.ops_ui import router as ops_ui_router
from app.api.routes.public_contact import router as public_contact_router
from app.api.routes.public_site import router as public_site_router
from app.api.routes.public_website_analytics import router as public_website_analytics_router
from app.api.routes.telegram_webhook import router as telegram_webhook_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.workers.tasks.production_invariant_alerts import run_production_invariant_monitor

_PRODUCTION_ENVIRONMENTS = frozenset({"prod", "production"})


@asynccontextmanager
async def app_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    monitor_task: asyncio.Task[None] | None = None
    app_env = str(get_settings().app_env).strip().lower()
    if app_env in _PRODUCTION_ENVIRONMENTS:
        monitor_task = asyncio.create_task(
            run_production_invariant_monitor(),
            name="production-invariant-monitor",
        )
    try:
        yield
    finally:
        if monitor_task is not None:
            monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await monitor_task


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    docs_enabled = bool(getattr(settings, "enable_openapi_docs", True))

    app = FastAPI(
        title="Quiz Arena Bot API",
        version="0.1.0",
        lifespan=app_lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    frontend_origin = str(getattr(settings, "admin_frontend_origin", "") or "").strip()
    if frontend_origin:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[frontend_origin],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def add_admin_noindex_header(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/admin"):
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    app.include_router(health_router)
    app.include_router(telegram_webhook_router)
    app.include_router(internal_promo_router)
    app.include_router(internal_offers_router)
    app.include_router(internal_referrals_router)
    app.include_router(internal_analytics_router)
    app.include_router(public_site_router)
    app.include_router(public_contact_router)
    app.include_router(public_website_analytics_router)
    app.include_router(ops_ui_router)
    app.include_router(admin_router)
    app.mount("/ops/static", StaticFiles(directory=str(OPS_UI_STATIC_DIR)), name="ops-static")
    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "dev",
    )


if __name__ == "__main__":
    run()
