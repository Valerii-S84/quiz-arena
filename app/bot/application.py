from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from app.bot.handlers.gameplay import router as gameplay_router
from app.bot.handlers.payments import router as payments_router
from app.bot.handlers.promo import router as promo_router
from app.bot.handlers.start import router as start_router
from app.core.config import get_settings


def build_bot() -> Bot:
    settings = get_settings()
    return Bot(token=settings.telegram_bot_token, default=DefaultBotProperties())


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(start_router)
    dispatcher.include_router(gameplay_router)
    dispatcher.include_router(payments_router)
    dispatcher.include_router(promo_router)
    return dispatcher
