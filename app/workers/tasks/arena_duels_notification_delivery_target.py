from __future__ import annotations

from app.db.repo.production_reliability_types import TelegramDeliveryAttemptCreate
from app.game.arena_duels.types import ArenaBeatenNotification


def beaten_delivery_attempt(
    *,
    notification: ArenaBeatenNotification,
    telegram_user_id: int | None,
) -> TelegramDeliveryAttemptCreate:
    correlation_id = ":".join(
        (
            str(notification.arena_duel_id),
            str(notification.previous_best_attempt_id),
            str(notification.new_best_attempt_id),
        )
    )
    target_id = str(notification.previous_best_user_id)
    flow = "arena_beaten_notification"
    return TelegramDeliveryAttemptCreate(
        flow=flow,
        task_name="arena_duels.send_arena_beaten_notification_task",
        correlation_id=correlation_id,
        idempotency_key=(f"telegram-delivery:{flow}:{correlation_id}:user:{target_id}"),
        target_type="user",
        target_id=target_id,
        telegram_user_id=telegram_user_id,
        safe_context={
            "arena_duel_id": str(notification.arena_duel_id),
            "previous_best_user_id": notification.previous_best_user_id,
            "new_best_user_id": notification.new_best_user_id,
        },
    )


__all__ = ["beaten_delivery_attempt"]
