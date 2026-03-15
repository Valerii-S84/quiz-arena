from __future__ import annotations

from aiogram.types import CallbackQuery

from app.bot.handlers import gameplay_callbacks
from app.bot.handlers.gameplay_flows import friend_lobby_manage_flow
from app.bot.handlers.gameplay_friend_challenge_context import get_gameplay_module


async def handle_friend_open_repost(callback: CallbackQuery) -> None:
    gameplay = get_gameplay_module()
    await friend_lobby_manage_flow.handle_friend_open_repost(
        callback,
        friend_open_repost_re=gameplay_callbacks.FRIEND_OPEN_REPOST_RE,
        parse_uuid_callback=gameplay_callbacks.parse_uuid_callback,
        session_local=gameplay.SessionLocal,
        user_onboarding_service=gameplay.UserOnboardingService,
        game_session_service=gameplay.GameSessionService,
        build_friend_invite_link=gameplay._build_friend_invite_link,
        build_friend_plan_text=gameplay._build_friend_plan_text,
        build_friend_ttl_text=gameplay._build_friend_ttl_text,
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
