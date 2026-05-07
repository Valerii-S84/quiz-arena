from __future__ import annotations

from aiogram.types import CallbackQuery

from app.game.arena_duels import analytics as arena_analytics

from .arena_duel_flow_accept import handle_arena_accept_preview as _handle_arena_accept_preview
from .arena_duel_flow_challenge import (
    handle_arena_challenge_friend as _handle_arena_challenge_friend,
)
from .arena_duel_flow_list import handle_arena_open as _handle_arena_open
from .arena_duel_flow_publish import handle_arena_publish_friend as _handle_arena_publish_friend
from .arena_duel_flow_results import send_arena_completion_result as _send_arena_completion_result
from .arena_duel_flow_start import handle_arena_start_attempt as _handle_arena_start_attempt
from .arena_duel_flow_start import handle_arena_start_create as _handle_arena_start_create
from .arena_duel_flow_support import parse_arena_duel_id

ARENA_EVENT_ARENA_DUEL_PUBLISHED = arena_analytics.ARENA_EVENT_ARENA_DUEL_PUBLISHED
ARENA_EVENT_FRIEND_DUEL_PUBLISHED_TO_ARENA = (
    arena_analytics.ARENA_EVENT_FRIEND_DUEL_PUBLISHED_TO_ARENA
)
emit_arena_analytics_event = arena_analytics.emit_arena_analytics_event


async def handle_arena_open(callback: CallbackQuery, **kwargs) -> None:
    await _handle_arena_open(callback, **kwargs)


async def handle_arena_accept_preview(callback: CallbackQuery, **kwargs) -> None:
    await _handle_arena_accept_preview(callback, **kwargs)


async def handle_arena_start_create(callback: CallbackQuery, **kwargs) -> None:
    await _handle_arena_start_create(callback, **kwargs)


async def handle_arena_start_attempt(
    callback: CallbackQuery,
    *,
    arena_start_attempt_re,
    parse_uuid_callback,
    **kwargs,
) -> None:
    duel_id = parse_arena_duel_id(
        callback,
        pattern=arena_start_attempt_re,
        parse_uuid_callback=parse_uuid_callback,
    )
    if duel_id is None:
        from app.bot.texts.de import TEXTS_DE

        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await _handle_arena_start_attempt(
        callback,
        duel_id=duel_id,
        **kwargs,
    )


async def handle_arena_publish_friend(
    callback: CallbackQuery,
    *,
    arena_publish_friend_re,
    parse_uuid_callback,
    **kwargs,
) -> None:
    friend_challenge_id = parse_arena_duel_id(
        callback,
        pattern=arena_publish_friend_re,
        parse_uuid_callback=parse_uuid_callback,
    )
    if friend_challenge_id is None:
        from app.bot.texts.de import TEXTS_DE

        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await _handle_arena_publish_friend(
        callback,
        friend_challenge_id=friend_challenge_id,
        emit_arena_analytics_event=emit_arena_analytics_event,
        **kwargs,
    )


async def send_arena_completion_result(callback: CallbackQuery, **kwargs) -> None:
    await _send_arena_completion_result(
        callback,
        emit_arena_analytics_event=emit_arena_analytics_event,
        **kwargs,
    )


async def handle_arena_challenge_friend(
    callback: CallbackQuery,
    *,
    arena_challenge_friend_re,
    parse_uuid_callback,
    **kwargs,
) -> None:
    arena_duel_id = parse_arena_duel_id(
        callback,
        pattern=arena_challenge_friend_re,
        parse_uuid_callback=parse_uuid_callback,
    )
    if arena_duel_id is None:
        from app.bot.texts.de import TEXTS_DE

        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await _handle_arena_challenge_friend(callback, arena_duel_id=arena_duel_id, **kwargs)
