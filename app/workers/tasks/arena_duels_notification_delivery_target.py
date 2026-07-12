from __future__ import annotations

from app.game.arena_duels.types import ArenaBeatenNotification
from app.services.telegram_delivery import TelegramDeliveryTarget, build_delivery_idempotency_key


def _beaten_delivery_target(
    *,
    notification: ArenaBeatenNotification,
    telegram_user_id: int | None,
) -> TelegramDeliveryTarget:
    correlation_id = ":".join(
        (
            str(notification.arena_duel_id),
            str(notification.previous_best_attempt_id),
            str(notification.new_best_attempt_id),
        )
    )
    target_id = str(notification.previous_best_user_id)
    return TelegramDeliveryTarget(
        flow="arena_beaten_notification",
        task_name="arena_duels.send_arena_beaten_notification_task",
        correlation_id=correlation_id,
        target_type="user",
        target_id=target_id,
        idempotency_key=build_delivery_idempotency_key(
            flow="arena_beaten_notification",
            correlation_id=correlation_id,
            target_type="user",
            target_id=target_id,
        ),
        telegram_user_id=telegram_user_id,
        chat_id=telegram_user_id,
        safe_context={
            "arena_duel_id": str(notification.arena_duel_id),
            "previous_best_user_id": notification.previous_best_user_id,
            "new_best_user_id": notification.new_best_user_id,
        },
    )
