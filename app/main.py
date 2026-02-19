import uvicorn
from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.internal_offers import router as internal_offers_router
from app.api.routes.internal_promo import router as internal_promo_router
from app.api.routes.internal_referrals import router as internal_referrals_router
from app.api.routes.telegram_webhook import router as telegram_webhook_router
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Quiz Arena Bot API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.include_router(health_router)
    app.include_router(telegram_webhook_router)
    app.include_router(internal_promo_router)
    app.include_router(internal_offers_router)
    app.include_router(internal_referrals_router)
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
