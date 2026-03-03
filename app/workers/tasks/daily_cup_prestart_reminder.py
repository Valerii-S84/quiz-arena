from __future__ import annotations

import structlog
from aiogram.exceptions import TelegramForbiddenError

from app.bot.application import build_bot
from app.bot.keyboards.daily_cup import build_daily_cup_lobby_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import TOURNAMENT_STATUS_REGISTRATION
from app.workers.tasks.daily_cup_config import DAILY_CUP_PUSH_BATCH_SIZE
from app.workers.tasks.daily_cup_core import ensure_daily_cup_registration_tournament, now_utc

logger = structlog.get_logger("app.workers.tasks.daily_cup_prestart_reminder")


async def send_daily_cup_prestart_reminder_async() -> dict[str, int]:
    now_utc_value = now_utc()
    async with SessionLocal.begin() as session:
        tournament = await ensure_daily_cup_registration_tournament(
            session=session,
            now_utc_value=now_utc_value,
        )
        if tournament.status != TOURNAMENT_STATUS_REGISTRATION:
            return {"processed": 0, "users_scanned_total": 0, "sent_total": 0, "skipped_total": 0}

    scanned_total = sent_total = skipped_total = 0
    last_user_id: int | None = None
    text = TEXTS_DE["msg.daily_cup.prestart_reminder"]
    keyboard = build_daily_cup_lobby_keyboard(
        tournament_id=str(tournament.id),
        can_join=False,
        play_challenge_id=None,
        show_share_result=False,
    )

    bot = build_bot()
    try:
        while True:
            async with SessionLocal.begin() as session:
                targets = await UsersRepo.list_daily_cup_registered_reminder_targets(
                    session,
                    tournament_id=tournament.id,
                    after_user_id=last_user_id,
                    limit=DAILY_CUP_PUSH_BATCH_SIZE,
                )
            if not targets:
                break
            for user_id, telegram_user_id in targets:
                scanned_total += 1
                last_user_id = user_id
                try:
                    await bot.send_message(
                        chat_id=telegram_user_id,
                        text=text,
                        reply_markup=keyboard,
                    )
                    sent_total += 1
                except TelegramForbiddenError:
                    skipped_total += 1
                except Exception:
                    skipped_total += 1
    finally:
        await bot.session.close()
    result = {
        "processed": 1,
        "users_scanned_total": scanned_total,
        "sent_total": sent_total,
        "skipped_total": skipped_total,
    }
    logger.info("daily_cup_prestart_reminder_processed", **result)
    return result


__all__ = ["send_daily_cup_prestart_reminder_async"]
