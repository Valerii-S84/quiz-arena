from __future__ import annotations

from typing import Any

from app.services.telegram_delivery import TelegramDeliveryTarget, build_delivery_idempotency_key
from app.workers.tasks.tournaments_messaging_delivery_types import TournamentRoundDeliveryContext


def private_round_delivery_target(
    *,
    delivery_context: TournamentRoundDeliveryContext,
    user_id: int,
    chat_id: int | None,
    delivery_operation: str,
    pending_replay_safe: bool,
) -> TelegramDeliveryTarget:
    context = delivery_context.request.context
    target_id = f"{user_id}:phase:{delivery_context.content_version}:{delivery_operation}"
    return TelegramDeliveryTarget(
        flow=delivery_context.flow,
        task_name=delivery_context.task_name,
        correlation_id=delivery_context.correlation_id,
        target_type="user",
        target_id=target_id,
        idempotency_key=build_delivery_idempotency_key(
            flow=delivery_context.flow,
            correlation_id=delivery_context.correlation_id,
            target_type="user",
            target_id=target_id,
        ),
        telegram_user_id=chat_id,
        chat_id=chat_id,
        safe_context={
            "tournament_id": delivery_context.correlation_id,
            "user_id": user_id,
            "status": str(context.tournament.status),
            "current_round": int(context.tournament.current_round),
            "content_version": delivery_context.content_version,
            "pending_replay_safe": pending_replay_safe,
        },
    )


def private_round_content_version(*, tournament: Any) -> str:
    status = str(tournament.status).lower()
    if status == "completed":
        return "status:completed"
    return f"round:{max(1, int(tournament.current_round))}:status:{status}"


def delivery_operation(existing_message_id: int | None) -> str:
    if existing_message_id is None:
        return "send"
    return f"edit:{int(existing_message_id)}"


def fallback_delivery_operation(existing_message_id: int) -> str:
    return f"fallback_send_after_edit:{int(existing_message_id)}"
