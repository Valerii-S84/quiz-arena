from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

import app.bot.handlers.gameplay_flows.arena_duel_flow as arena_duel_flow
from app.bot.handlers import gameplay_callbacks
from app.bot.handlers.gameplay_views import _build_question_text
from app.bot.keyboards.duels import (
    build_arena_create_keyboard,
    build_duels_menu_keyboard,
    build_friend_duel_keyboard,
)
from app.bot.texts.de import TEXTS_DE
from app.db.session import SessionLocal
from app.game.arena_duels.accept import accept_arena_duel, get_arena_duel_accept_preview
from app.game.arena_duels.service import create_arena_duel_baseline, list_active_arena_duels
from app.game.duels.constants import (
    ARENA_CREATE_CALLBACK,
    ARENA_LIST_CALLBACK,
    ARENA_START_CREATE_CALLBACK,
    DUEL_ARENA_CALLBACK,
    DUEL_FRIEND_CALLBACK,
    DUEL_MENU_CALLBACK,
)
from app.services.user_onboarding import UserOnboardingService


async def handle_duels_menu(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await callback.message.answer(
        TEXTS_DE["msg.duels.menu"],
        reply_markup=build_duels_menu_keyboard(),
    )
    await callback.answer()


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
        accept_arena_duel=accept_arena_duel,
        build_question_text=_build_question_text,
    )


async def handle_friend_duel_open(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await callback.message.answer(
        TEXTS_DE["msg.duels.friend"],
        reply_markup=build_friend_duel_keyboard(),
    )
    await callback.answer()


def register(router: Router) -> None:
    router.callback_query(F.data == DUEL_MENU_CALLBACK)(handle_duels_menu)
    router.callback_query((F.data == DUEL_ARENA_CALLBACK) | (F.data == ARENA_LIST_CALLBACK))(
        handle_arena_open
    )
    router.callback_query(F.data == ARENA_CREATE_CALLBACK)(handle_arena_create)
    router.callback_query(F.data == ARENA_START_CREATE_CALLBACK)(handle_arena_start_create)
    router.callback_query(F.data.regexp(gameplay_callbacks.ARENA_ACCEPT_RE))(
        handle_arena_accept_preview
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.ARENA_START_ATTEMPT_RE))(
        handle_arena_start_attempt
    )
    router.callback_query(F.data == DUEL_FRIEND_CALLBACK)(handle_friend_duel_open)
