from __future__ import annotations

from app.services.telegram_delivery import TelegramDeliveryTarget, build_delivery_idempotency_key


def daily_cup_delivery_target(
    *,
    flow: str,
    task_name: str,
    tournament_id_text: str,
    user_id: int,
    telegram_user_id: int,
) -> TelegramDeliveryTarget:
    return TelegramDeliveryTarget(
        flow=flow,
        task_name=task_name,
        correlation_id=tournament_id_text,
        target_type="user",
        target_id=str(user_id),
        idempotency_key=build_delivery_idempotency_key(
            flow=flow,
            correlation_id=tournament_id_text,
            target_type="user",
            target_id=str(user_id),
        ),
        telegram_user_id=telegram_user_id,
        chat_id=telegram_user_id,
        safe_context={"tournament_id": tournament_id_text, "user_id": user_id},
    )
