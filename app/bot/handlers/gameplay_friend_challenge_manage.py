from __future__ import annotations

from aiogram.types import CallbackQuery

from app.bot.handlers import gameplay_callbacks
from app.bot.handlers.gameplay_flows import friend_lobby_manage_flow
from app.bot.handlers.gameplay_friend_challenge_context import get_gameplay_module
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.duels import rollout as duel_rollout


async def _answer_duels_disabled(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer(TEXTS_DE["msg.duels.disabled"], show_alert=True)
        return
    await callback.message.answer(
        TEXTS_DE["msg.duels.disabled"],
        reply_markup=build_home_keyboard(),
    )
    await callback.answer()


async def handle_friend_open_repost(callback: CallbackQuery) -> None:
    if not duel_rollout.is_canonical_duels_enabled():
        await _answer_duels_disabled(callback)
        return
    await friend_lobby_manage_flow.handle_friend_open_repost(
        callback,
        friend_open_repost_re=gameplay_callbacks.FRIEND_OPEN_REPOST_RE,
        parse_uuid_callback=gameplay_callbacks.parse_uuid_callback,
    )


async def handle_friend_delete(callback: CallbackQuery) -> None:
    gameplay = get_gameplay_module()
    await friend_lobby_manage_flow.handle_friend_delete(
        callback,
        friend_delete_re=gameplay_callbacks.FRIEND_DELETE_RE,
        parse_uuid_callback=gameplay_callbacks.parse_uuid_callback,
        session_local=gameplay.SessionLocal,
        user_onboarding_service=gameplay.UserOnboardingService,
        game_session_service=gameplay.GameSessionService,
    )
