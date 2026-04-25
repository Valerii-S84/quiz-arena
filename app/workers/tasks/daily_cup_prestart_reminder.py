from __future__ import annotations

import structlog

from app.bot.application import build_bot
from app.workers.tasks.daily_cup_core import now_utc
from app.workers.tasks.daily_cup_registration_push import send_daily_cup_registration_push_async

logger = structlog.get_logger("app.workers.tasks.daily_cup_prestart_reminder")


async def send_daily_cup_prestart_reminder_async() -> dict[str, int]:
    return await send_daily_cup_registration_push_async(
        now_utc_factory=now_utc,
        bot_factory=build_bot,
        text_key="msg.daily_cup.prestart_reminder",
        log_event="daily_cup_prestart_reminder_processed",
        sent_event_type="daily_cup_prestart_reminder_sent",
        logger=logger,
    )


__all__ = ["send_daily_cup_prestart_reminder_async"]
