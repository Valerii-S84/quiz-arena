from __future__ import annotations

from aiogram.types import CallbackQuery

from app.bot.handlers import gameplay_callbacks
from app.bot.handlers.gameplay_flows import friend_lobby_flow
from app.bot.handlers.gameplay_friend_challenge_context import get_gameplay_module
from app.bot.keyboards.friend_challenge import build_friend_challenge_create_keyboard
from app.bot.keyboards.tournament import build_tournament_format_keyboard
from app.bot.texts.de import TEXTS_DE


async def handle_friend_challenge_create(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await callback.message.answer(
        TEXTS_DE["msg.friend.challenge.create.choose"],
        reply_markup=build_friend_challenge_create_keyboard(),
    )
    await callback.answer()


async def handle_create_tournament_start(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await callback.message.answer(
        TEXTS_DE["msg.friend.challenge.tournament.format"],
        reply_markup=build_tournament_format_keyboard(),
    )
    await callback.answer()


async def handle_friend_challenge_type_selected(callback: CallbackQuery) -> None:
    await friend_lobby_flow.handle_friend_challenge_type_selected(
        callback,
        friend_create_type_re=gameplay_callbacks.FRIEND_CREATE_TYPE_RE,
    )


async def handle_friend_challenge_create_selected(callback: CallbackQuery) -> None:
    gameplay = get_gameplay_module()
    await friend_lobby_flow.handle_friend_challenge_create_selected(
        callback,
        session_local=gameplay.SessionLocal,
        user_onboarding_service=gameplay.UserOnboardingService,
        game_session_service=gameplay.GameSessionService,
        parse_friend_create_format=gameplay_callbacks.parse_friend_create_format,
        build_friend_invite_link=gameplay._build_friend_invite_link,
        build_friend_plan_text=gameplay._build_friend_plan_text,
        build_friend_ttl_text=gameplay._build_friend_ttl_text,
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
