from __future__ import annotations

from datetime import datetime

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.arena_duel_flow import send_arena_completion_result
from app.bot.handlers.gameplay_flows.play_flow_context import ContinueModeFlowServices
from app.bot.handlers.gameplay_flows.play_flow_continue import ContinueOutcome
from app.core.analytics_events import EVENT_SOURCE_BOT
from app.game.arena_duels.types import ArenaBeatenNotification


async def handle_arena_completion(
    callback: CallbackQuery,
    outcome: ContinueOutcome,
    now_utc: datetime,
    services: ContinueModeFlowServices,
) -> None:
    await callback.answer()
    if outcome.arena_completion is not None:
        await send_arena_completion_result(
            callback,
            completion=outcome.arena_completion,
            session_local=services.session_local,
            user_onboarding_service=services.user_onboarding_service,
        )
    if outcome.arena_notification is not None:
        await _send_arena_beaten_notification_best_effort(
            notification=outcome.arena_notification,
            happened_at=now_utc,
            bot=callback.bot,
            event_logger=services.event_logger,
        )


async def _send_arena_beaten_notification_best_effort(
    *,
    notification: ArenaBeatenNotification,
    happened_at: datetime,
    bot,
    event_logger,
) -> None:
    try:
        from app.workers.tasks.arena_duels import send_arena_beaten_notification

        await send_arena_beaten_notification(
            notification=notification,
            happened_at=happened_at,
            bot=bot,
            source=EVENT_SOURCE_BOT,
        )
    except Exception as exc:
        event_logger.warning(
            "arena_beaten_notification_failed",
            arena_duel_id=str(notification.arena_duel_id),
            previous_best_attempt_id=str(notification.previous_best_attempt_id),
            new_best_attempt_id=str(notification.new_best_attempt_id),
            error_type=type(exc).__name__,
        )
