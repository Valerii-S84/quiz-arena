from __future__ import annotations

from aiogram.types import CallbackQuery

import app.bot.handlers.gameplay_flows.arena_duel_flow as arena_duel_flow
from app.bot.handlers import gameplay_callbacks, gameplay_helpers
from app.bot.handlers.gameplay_views import _build_question_text
from app.bot.keyboards.duels import build_arena_create_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.session import SessionLocal
from app.game.arena_duels.accept import accept_arena_duel, get_arena_duel_accept_preview
from app.game.arena_duels.service import (
    create_arena_duel_baseline,
    create_friend_challenge_from_arena_duel,
    list_active_arena_duels,
)
from app.game.duels.limits import DuelLimitService
from app.game.sessions.service import GameSessionService
from app.game.sessions.service.friend_challenges_manage import publish_friend_challenge_to_arena
from app.services.user_onboarding import UserOnboardingService


async def handle_arena_open(callback: CallbackQuery) -> None:
    await arena_duel_flow.handle_arena_open(
        callback,
        session_local=SessionLocal,
        user_onboarding_service=UserOnboardingService,
        list_active_arena_duels=list_active_arena_duels,
    )


async def handle_arena_create(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await callback.message.answer(
        TEXTS_DE["msg.duels.arena.create"],
        reply_markup=build_arena_create_keyboard(),
    )
    await callback.answer()


async def handle_arena_start_create(callback: CallbackQuery) -> None:
    await arena_duel_flow.handle_arena_start_create(
        callback,
        session_local=SessionLocal,
        user_onboarding_service=UserOnboardingService,
        resolve_arena_create_access_type=DuelLimitService.resolve_arena_create_access_type,
        create_arena_duel_baseline=create_arena_duel_baseline,
        build_question_text=_build_question_text,
    )


async def handle_arena_accept_preview(callback: CallbackQuery) -> None:
    await arena_duel_flow.handle_arena_accept_preview(
        callback,
        arena_accept_re=gameplay_callbacks.ARENA_ACCEPT_RE,
        parse_uuid_callback=gameplay_callbacks.parse_uuid_callback,
        session_local=SessionLocal,
        user_onboarding_service=UserOnboardingService,
        get_arena_duel_accept_preview=get_arena_duel_accept_preview,
    )


async def handle_arena_start_attempt(callback: CallbackQuery) -> None:
    await arena_duel_flow.handle_arena_start_attempt(
        callback,
        arena_start_attempt_re=gameplay_callbacks.ARENA_START_ATTEMPT_RE,
        parse_uuid_callback=gameplay_callbacks.parse_uuid_callback,
        session_local=SessionLocal,
        user_onboarding_service=UserOnboardingService,
        resolve_arena_accept_access_type=DuelLimitService.resolve_arena_accept_access_type,
        accept_arena_duel=accept_arena_duel,
        build_question_text=_build_question_text,
    )


async def handle_arena_publish_friend(callback: CallbackQuery) -> None:
    await arena_duel_flow.handle_arena_publish_friend(
        callback,
        arena_publish_friend_re=gameplay_callbacks.ARENA_PUBLISH_FRIEND_RE,
        parse_uuid_callback=gameplay_callbacks.parse_uuid_callback,
        session_local=SessionLocal,
        user_onboarding_service=UserOnboardingService,
        publish_friend_challenge_to_arena=publish_friend_challenge_to_arena,
        start_friend_challenge_round=GameSessionService.start_friend_challenge_round,
        build_question_text=_build_question_text,
    )


async def handle_arena_challenge_friend(callback: CallbackQuery) -> None:
    await arena_duel_flow.handle_arena_challenge_friend(
        callback,
        arena_challenge_friend_re=gameplay_callbacks.ARENA_CHALLENGE_FRIEND_RE,
        parse_uuid_callback=gameplay_callbacks.parse_uuid_callback,
        session_local=SessionLocal,
        user_onboarding_service=UserOnboardingService,
        create_friend_challenge_from_arena_duel=create_friend_challenge_from_arena_duel,
        build_friend_invite_link=gameplay_helpers._build_friend_invite_link,
    )
