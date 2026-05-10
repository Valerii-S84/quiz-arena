from __future__ import annotations

from aiogram.types import CallbackQuery

from app.bot.handlers import gameplay_callbacks, gameplay_views
from app.bot.handlers.gameplay_flows import friend_lobby_flow
from app.bot.handlers.gameplay_friend_challenge_context import get_gameplay_module
from app.bot.keyboards.duels import build_friend_duel_keyboard
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


async def handle_friend_challenge_create(callback: CallbackQuery) -> None:
    if not duel_rollout.is_canonical_duels_enabled():
        await _answer_duels_disabled(callback)
        return
    if callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await callback.message.answer(
        TEXTS_DE["msg.duels.friend"],
        reply_markup=build_friend_duel_keyboard(),
    )
    await callback.answer()


async def handle_friend_challenge_type_selected(callback: CallbackQuery) -> None:
    if not duel_rollout.is_canonical_duels_enabled():
        await _answer_duels_disabled(callback)
        return
    await friend_lobby_flow.handle_friend_challenge_type_selected(
        callback,
        friend_create_type_re=gameplay_callbacks.FRIEND_CREATE_TYPE_RE,
    )


async def handle_friend_challenge_create_selected(callback: CallbackQuery) -> None:
    if not duel_rollout.is_canonical_duels_enabled():
        await _answer_duels_disabled(callback)
        return
    gameplay = get_gameplay_module()
    await friend_lobby_flow.handle_friend_challenge_create_selected(
        callback,
        session_local=gameplay.SessionLocal,
        user_onboarding_service=gameplay.UserOnboardingService,
        game_session_service=gameplay.GameSessionService,
        parse_friend_create_format=gameplay_callbacks.parse_friend_create_format,
        build_friend_invite_link=gameplay._build_friend_invite_link,
        build_friend_plan_text=gameplay_views._build_friend_plan_text,
        build_friend_ttl_text=gameplay_views._build_friend_ttl_text,
    )


async def handle_friend_challenge_copy_link(callback: CallbackQuery) -> None:
    gameplay = get_gameplay_module()
    await friend_lobby_flow.handle_friend_copy_link(
        callback,
        friend_copy_link_re=gameplay_callbacks.FRIEND_COPY_LINK_RE,
        parse_uuid_callback=gameplay_callbacks.parse_uuid_callback,
        session_local=gameplay.SessionLocal,
        user_onboarding_service=gameplay.UserOnboardingService,
        game_session_service=gameplay.GameSessionService,
        build_friend_invite_link=gameplay._build_friend_invite_link,
    )


async def handle_friend_my_duels(callback: CallbackQuery) -> None:
    if not duel_rollout.is_canonical_duels_enabled():
        await _answer_duels_disabled(callback)
        return
    gameplay = get_gameplay_module()
    await friend_lobby_flow.handle_friend_my_duels(
        callback,
        session_local=gameplay.SessionLocal,
        user_onboarding_service=gameplay.UserOnboardingService,
        game_session_service=gameplay.GameSessionService,
        resolve_opponent_label=gameplay._resolve_opponent_label,
    )


async def handle_friend_challenge_invite_sent(callback: CallbackQuery) -> None:
    await friend_lobby_flow.handle_friend_challenge_invite_sent(
        callback,
        friend_invite_sent_re=gameplay_callbacks.FRIEND_INVITE_SENT_RE,
        parse_uuid_callback=gameplay_callbacks.parse_uuid_callback,
    )


async def handle_friend_challenge_invite_required(callback: CallbackQuery) -> None:
    await callback.answer(TEXTS_DE["msg.friend.challenge.invite.confirm.first"])
