from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from app.bot.handlers.start import router as start_router
from app.core.config import get_settings


def build_bot() -> Bot:
    settings = get_settings()
    return Bot(token=settings.telegram_bot_token, default=DefaultBotProperties())


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(start_router)
    return dispatcher
