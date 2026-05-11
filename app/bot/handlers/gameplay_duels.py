from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

import app.bot.handlers.gameplay_flows.arena_duel_flow as arena_duel_flow
import app.bot.handlers.gameplay_flows.arena_revanche_flow as arena_revanche_flow
from app.bot.handlers import gameplay_callbacks
from app.bot.handlers.gameplay_flows import (
    duels_arena_router_flow,
    duels_menu_flow,
    duels_revanche_router_flow,
)
from app.db.session import SessionLocal
from app.game.arena_duels.analytics import (
    ARENA_EVENT_DUEL_MENU_OPENED,
    ARENA_EVENT_DUEL_MODE_SELECTED,
    ARENA_EVENT_FRIEND_DUEL_OPENED,
    build_arena_event_payload,
    emit_arena_analytics_event,
)
from app.game.arena_duels.revanche import (
    cleanup_arena_revanche_request,
    load_arena_revanche_context,
    prepare_arena_revanche_request,
    record_arena_revanche_sent,
)
from app.game.duels import rollout as duel_rollout
from app.game.duels.constants import (
    ARENA_CREATE_CALLBACK,
    ARENA_LIST_CALLBACK,
    ARENA_START_CREATE_CALLBACK,
    DUEL_ARENA_CALLBACK,
    DUEL_FRIEND_CALLBACK,
    DUEL_MENU_CALLBACK,
)
from app.game.sessions.service.friend_challenges_manage import publish_friend_challenge_to_arena
from app.services.user_onboarding import UserOnboardingService

__all__ = [
    "arena_duel_flow",
    "arena_revanche_flow",
    "build_arena_event_payload",
    "cleanup_arena_revanche_request",
    "load_arena_revanche_context",
    "prepare_arena_revanche_request",
    "publish_friend_challenge_to_arena",
    "record_arena_revanche_sent",
]


async def _require_duels_enabled(callback: CallbackQuery) -> bool:
    if duel_rollout.is_canonical_duels_enabled():
        return True
    await duels_menu_flow.answer_duels_disabled(callback)
    return False


async def handle_duels_menu(callback: CallbackQuery, *, emit_event: bool = False) -> None:
    if not await _require_duels_enabled(callback):
        return
    await duels_menu_flow.handle_duels_menu(
        callback,
        emit_event=emit_event,
        session_local=SessionLocal,
        user_onboarding_service=UserOnboardingService,
        emit_arena_analytics_event=emit_arena_analytics_event,
        duel_menu_opened_event=ARENA_EVENT_DUEL_MENU_OPENED,
    )


async def handle_arena_open(callback: CallbackQuery) -> None:
    if not await _require_duels_enabled(callback):
        return
    if callback.data == DUEL_ARENA_CALLBACK:
        await duels_menu_flow.emit_duel_callback_events(
            callback,
            events=((ARENA_EVENT_DUEL_MODE_SELECTED, "arena"),),
            session_local=SessionLocal,
            user_onboarding_service=UserOnboardingService,
            emit_arena_analytics_event=emit_arena_analytics_event,
        )
    await duels_arena_router_flow.handle_arena_open(callback)


async def handle_arena_create(callback: CallbackQuery) -> None:
    if await _require_duels_enabled(callback):
        await duels_arena_router_flow.handle_arena_create(callback)


async def handle_arena_start_create(callback: CallbackQuery) -> None:
    if await _require_duels_enabled(callback):
        await duels_arena_router_flow.handle_arena_start_create(callback)


async def handle_arena_accept_preview(callback: CallbackQuery) -> None:
    if await _require_duels_enabled(callback):
        await duels_arena_router_flow.handle_arena_accept_preview(callback)


async def handle_arena_start_attempt(callback: CallbackQuery) -> None:
    if await _require_duels_enabled(callback):
        await duels_arena_router_flow.handle_arena_start_attempt(callback)


async def handle_arena_publish_friend(callback: CallbackQuery) -> None:
    if await _require_duels_enabled(callback):
        await duels_arena_router_flow.handle_arena_publish_friend(callback)


async def handle_arena_challenge_friend(callback: CallbackQuery) -> None:
    if await _require_duels_enabled(callback):
        await duels_arena_router_flow.handle_arena_challenge_friend(callback)


async def handle_arena_revanche_confirm(callback: CallbackQuery) -> None:
    if await _require_duels_enabled(callback):
        await duels_revanche_router_flow.handle_arena_revanche_confirm(callback)


async def handle_arena_revanche_send(callback: CallbackQuery) -> None:
    if await _require_duels_enabled(callback):
        await duels_revanche_router_flow.handle_arena_revanche_send(callback)


async def handle_friend_duel_open(callback: CallbackQuery, *, emit_event: bool = False) -> None:
    if not await _require_duels_enabled(callback):
        return
    await duels_menu_flow.handle_friend_duel_open(
        callback,
        emit_event=emit_event,
        session_local=SessionLocal,
        user_onboarding_service=UserOnboardingService,
        emit_arena_analytics_event=emit_arena_analytics_event,
        duel_mode_selected_event=ARENA_EVENT_DUEL_MODE_SELECTED,
        friend_duel_opened_event=ARENA_EVENT_FRIEND_DUEL_OPENED,
    )


async def _handle_duels_menu_registered(callback: CallbackQuery) -> None:
    await handle_duels_menu(callback, emit_event=True)


async def _handle_friend_duel_open_registered(callback: CallbackQuery) -> None:
    await handle_friend_duel_open(callback, emit_event=True)


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
    router.callback_query(F.data.regexp(gameplay_callbacks.ARENA_CHALLENGE_FRIEND_RE))(
        handle_arena_challenge_friend
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.ARENA_REVANCHE_RE))(
        handle_arena_revanche_confirm
    )
    router.callback_query(F.data.regexp(gameplay_callbacks.ARENA_REVANCHE_SEND_RE))(
        handle_arena_revanche_send
    )
    router.callback_query(F.data == DUEL_FRIEND_CALLBACK)(_handle_friend_duel_open_registered)
