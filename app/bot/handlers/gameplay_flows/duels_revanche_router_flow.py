from __future__ import annotations

from aiogram.types import CallbackQuery

import app.bot.handlers.gameplay_flows.arena_revanche_flow as arena_revanche_flow
from app.bot.handlers import gameplay_callbacks
from app.db.session import SessionLocal
from app.game.arena_duels.revanche import (
    cleanup_arena_revanche_request,
    load_arena_revanche_context,
    prepare_arena_revanche_request,
    record_arena_revanche_sent,
)
from app.services.user_onboarding import UserOnboardingService


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
