from __future__ import annotations

from collections.abc import Callable

from app.services.telegram_delivery import TelegramDeliveryTarget
from app.workers.tasks.daily_cup_turn_reminder_delivery_types import ReminderItem


def build_turn_reminder_delivery_target(
    *,
    reminder: ReminderItem,
    build_delivery_idempotency_key_fn: Callable[..., str],
) -> TelegramDeliveryTarget:
    target_id = f"{reminder.challenge_id}:{reminder.target_user_id}:{reminder.window_key}"
    correlation_id = str(reminder.tournament_id)
    return TelegramDeliveryTarget(
        flow="daily_cup_turn_reminder",
        task_name="daily_cup.send_turn_reminders",
        correlation_id=correlation_id,
        target_type="challenge_user",
        target_id=target_id,
        idempotency_key=build_delivery_idempotency_key_fn(
            flow="daily_cup_turn_reminder",
            correlation_id=correlation_id,
            target_type="challenge_user",
            target_id=target_id,
        ),
        telegram_user_id=reminder.target_chat_id,
        chat_id=reminder.target_chat_id,
        safe_context={
            "tournament_id": correlation_id,
            "challenge_id": reminder.challenge_id,
            "target_user_id": reminder.target_user_id,
            "window_key": reminder.window_key,
        },
    )


__all__ = ["build_turn_reminder_delivery_target"]
