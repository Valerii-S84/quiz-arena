from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery

import app.bot.handlers.gameplay_flows.arena_duel_flow as arena_duel_flow
import app.bot.handlers.gameplay_flows.arena_revanche_flow as arena_revanche_flow
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
from app.game.arena_duels.analytics import (
    ARENA_EVENT_DUEL_MENU_OPENED,
    ARENA_EVENT_DUEL_MODE_SELECTED,
    build_arena_event_payload,
    emit_arena_analytics_event,
)
from app.game.arena_duels.revanche import (
    cleanup_arena_revanche_request,
    load_arena_revanche_context,
    prepare_arena_revanche_request,
    record_arena_revanche_sent,
)
from app.game.arena_duels.service import create_arena_duel_baseline, list_active_arena_duels
from app.game.duels.constants import (
    ARENA_CREATE_CALLBACK,
    ARENA_LIST_CALLBACK,
    ARENA_START_CREATE_CALLBACK,
    DUEL_ARENA_CALLBACK,
    DUEL_FRIEND_CALLBACK,
    DUEL_MENU_CALLBACK,
)
from app.game.duels.limits import DuelLimitService
from app.game.sessions.service.friend_challenges_manage import publish_friend_challenge_to_arena
from app.services.user_onboarding import UserOnboardingService


async def handle_duels_menu(callback: CallbackQuery, *, emit_event: bool = False) -> None:
    if callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    if emit_event:
        await _emit_duel_callback_event(
            callback,
            event_type=ARENA_EVENT_DUEL_MENU_OPENED,
            action="menu",
        )
    await callback.message.answer(
        TEXTS_DE["msg.duels.menu"],
        reply_markup=build_duels_menu_keyboard(),
    )
    await callback.answer()


async def handle_arena_open(callback: CallbackQuery) -> None:
    if callback.data == DUEL_ARENA_CALLBACK:
        await _emit_duel_callback_event(
            callback,
            event_type=ARENA_EVENT_DUEL_MODE_SELECTED,
            action="arena",
        )
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
    )


async def handle_arena_revanche_confirm(callback: CallbackQuery) -> None:
    await arena_revanche_flow.handle_arena_revanche_confirm(
        callback,
        arena_revanche_re=gameplay_callbacks.ARENA_REVANCHE_RE,
        parse_uuid_callback=gameplay_callbacks.parse_uuid_callback,
        session_local=SessionLocal,
        user_onboarding_service=UserOnboardingService,
        load_arena_revanche_context=load_arena_revanche_context,
    )


async def handle_arena_revanche_send(callback: CallbackQuery) -> None:
    await arena_revanche_flow.handle_arena_revanche_send(
        callback,
        arena_revanche_send_re=gameplay_callbacks.ARENA_REVANCHE_SEND_RE,
        parse_uuid_callback=gameplay_callbacks.parse_uuid_callback,
        session_local=SessionLocal,
        user_onboarding_service=UserOnboardingService,
        prepare_arena_revanche_request=prepare_arena_revanche_request,
        record_arena_revanche_sent=record_arena_revanche_sent,
        cleanup_arena_revanche_request=cleanup_arena_revanche_request,
    )


async def handle_friend_duel_open(callback: CallbackQuery, *, emit_event: bool = False) -> None:
    if callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    if emit_event:
        await _emit_duel_callback_event(
            callback,
            event_type=ARENA_EVENT_DUEL_MODE_SELECTED,
            action="friend",
        )
    await callback.message.answer(
        TEXTS_DE["msg.duels.friend"],
        reply_markup=build_friend_duel_keyboard(),
    )
    await callback.answer()


async def _handle_duels_menu_registered(callback: CallbackQuery) -> None:
    await handle_duels_menu(callback, emit_event=True)


async def _handle_friend_duel_open_registered(callback: CallbackQuery) -> None:
    await handle_friend_duel_open(callback, emit_event=True)


async def _emit_duel_callback_event(
    callback: CallbackQuery,
    *,
    event_type: str,
    action: str,
) -> None:
    if callback.from_user is None:
        return
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        await emit_arena_analytics_event(
            session,
            event_type=event_type,
            happened_at=now_utc,
            user_id=snapshot.user_id,
            payload=build_arena_event_payload(user_id=snapshot.user_id, action=action),
        )


def register(router: Router) -> None:
    router.callback_query(F.data == DUEL_MENU_CALLBACK)(_handle_duels_menu_registered)
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
    router.callback_query(F.data.regexp(gameplay_callbacks.ARENA_PUBLISH_FRIEND_RE))(
        handle_arena_publish_friend
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.ARENA_REVANCHE_RE))(
        handle_arena_revanche_confirm
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.ARENA_REVANCHE_SEND_RE))(
        handle_arena_revanche_send
    )
    router.callback_query(F.data == DUEL_FRIEND_CALLBACK)(_handle_friend_duel_open_registered)
