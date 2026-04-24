from __future__ import annotations

from typing import cast
from uuid import UUID

from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.daily import build_daily_result_keyboard
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import SessionNotFoundError


def _build_daily_result_text(*, score: int) -> str:
    if score >= 7:
        return TEXTS_DE["msg.daily.result.reward.ticket"]
    if score == 6:
        return TEXTS_DE["msg.daily.result.reward.energy3"]
    if score == 5:
        return TEXTS_DE["msg.daily.result.reward.energy2"]
    return TEXTS_DE["msg.daily.result.reward.none"]


async def handle_daily_result_screen(
    callback: CallbackQuery,
    *,
    daily_run_id: UUID,
    session_local,
    user_onboarding_service,
    game_session_service,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    message = cast(Message, callback.message)

    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        try:
            summary = await game_session_service.get_daily_run_summary(
                session,
                user_id=snapshot.user_id,
                daily_run_id=daily_run_id,
            )
        except SessionNotFoundError:
            await message.answer(
                TEXTS_DE["msg.game.session.not_found"],
                reply_markup=build_home_keyboard(),
            )
            await callback.answer()
            return

    if summary.status != "COMPLETED":
        await message.answer(
            TEXTS_DE["msg.daily.challenge.used"],
            reply_markup=build_home_keyboard(),
        )
        await callback.answer()
        return

    await message.answer(
        _build_daily_result_text(score=summary.score),
        reply_markup=build_daily_result_keyboard(daily_run_id=str(summary.daily_run_id)),
    )
    await callback.answer()
