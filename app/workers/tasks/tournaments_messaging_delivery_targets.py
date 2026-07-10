from __future__ import annotations

from typing import Any

from app.services.telegram_delivery import TelegramDeliveryTarget, build_delivery_idempotency_key


def private_round_delivery_target(
    *,
    flow: str,
    task_name: str,
    correlation_id: str,
    user_id: int,
    chat_id: int | None,
    delivery_operation: str,
    content_version: str,
    tournament_status: str,
    current_round: int,
    pending_replay_safe: bool,
) -> TelegramDeliveryTarget:
    target_id = f"{user_id}:phase:{content_version}:{delivery_operation}"
    return TelegramDeliveryTarget(
        flow=flow,
        task_name=task_name,
        correlation_id=correlation_id,
        target_type="user",
        target_id=target_id,
        idempotency_key=build_delivery_idempotency_key(
            flow=flow,
            correlation_id=correlation_id,
            target_type="user",
            target_id=target_id,
        ),
        telegram_user_id=chat_id,
        chat_id=chat_id,
        safe_context={
            "tournament_id": correlation_id,
            "user_id": user_id,
            "status": tournament_status,
            "current_round": current_round,
            "content_version": content_version,
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
