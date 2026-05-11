from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from aiogram.types import CallbackQuery

from app.bot.keyboards.duels import build_duels_menu_keyboard, build_friend_duel_keyboard
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.arena_duels.analytics import build_arena_event_payload

AnalyticsEmitter = Callable[..., Awaitable[None]]


async def answer_duels_disabled(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer(TEXTS_DE["msg.duels.disabled"], show_alert=True)
        return
    await callback.message.answer(
        TEXTS_DE["msg.duels.disabled"],
        reply_markup=build_home_keyboard(),
    )
    await callback.answer()


async def handle_duels_menu(
    callback: CallbackQuery,
    *,
    emit_event: bool,
    session_local: Any,
    user_onboarding_service: Any,
    emit_arena_analytics_event: AnalyticsEmitter,
    duel_menu_opened_event: str,
) -> None:
    if callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    if emit_event:
        await emit_duel_callback_events(
            callback,
            events=((duel_menu_opened_event, "menu"),),
            session_local=session_local,
            user_onboarding_service=user_onboarding_service,
            emit_arena_analytics_event=emit_arena_analytics_event,
        )
    await callback.message.answer(
        TEXTS_DE["msg.duels.menu"],
        reply_markup=build_duels_menu_keyboard(),
    )
    await callback.answer()


async def handle_friend_duel_open(
    callback: CallbackQuery,
    *,
    emit_event: bool,
    session_local: Any,
    user_onboarding_service: Any,
    emit_arena_analytics_event: AnalyticsEmitter,
    duel_mode_selected_event: str,
    friend_duel_opened_event: str,
) -> None:
    if callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    if emit_event:
        await emit_duel_callback_events(
            callback,
            events=((duel_mode_selected_event, "friend"), (friend_duel_opened_event, None)),
            session_local=session_local,
            user_onboarding_service=user_onboarding_service,
            emit_arena_analytics_event=emit_arena_analytics_event,
        )
    await callback.message.answer(
        TEXTS_DE["msg.duels.friend"],
        reply_markup=build_friend_duel_keyboard(),
    )
    await callback.answer()


async def emit_duel_callback_events(
    callback: CallbackQuery,
    *,
    events: tuple[tuple[str, str | None], ...],
    session_local: Any,
    user_onboarding_service: Any,
    emit_arena_analytics_event: AnalyticsEmitter,
) -> None:
    if callback.from_user is None:
        return
    now_utc = datetime.now(timezone.utc)
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        for event_type, action in events:
            await emit_arena_analytics_event(
                session,
                event_type=event_type,
                happened_at=now_utc,
                user_id=snapshot.user_id,
                payload=build_arena_event_payload(user_id=snapshot.user_id, action=action),
            )
