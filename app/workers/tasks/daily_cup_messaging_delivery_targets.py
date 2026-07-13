from __future__ import annotations

from dataclasses import dataclass

from app.db.models.tournaments import Tournament
from app.services.telegram_delivery import TelegramDeliveryTarget, build_delivery_idempotency_key


@dataclass(frozen=True, slots=True)
class DailyCupRoundDeliveryTargetContext:
    flow: str
    task_name: str
    correlation_id: str
    content_version: str
    tournament_status: str
    current_round: int


def daily_cup_round_delivery_target(
    *,
    context: DailyCupRoundDeliveryTargetContext,
    user_id: int,
    chat_id: int | None,
    delivery_operation: str,
    pending_replay_safe: bool,
) -> TelegramDeliveryTarget:
    target_id = f"{user_id}:phase:{context.content_version}:{delivery_operation}"
    return TelegramDeliveryTarget(
        flow=context.flow,
        task_name=context.task_name,
        correlation_id=context.correlation_id,
        target_type="user",
        target_id=target_id,
        idempotency_key=build_delivery_idempotency_key(
            flow=context.flow,
            correlation_id=context.correlation_id,
            target_type="user",
            target_id=target_id,
        ),
        telegram_user_id=chat_id,
        chat_id=chat_id,
        safe_context={
            "tournament_id": context.correlation_id,
            "user_id": user_id,
            "status": context.tournament_status,
            "current_round": context.current_round,
            "content_version": context.content_version,
            "pending_replay_safe": pending_replay_safe,
        },
    )


def daily_cup_content_version(*, tournament: Tournament) -> str:
    status = str(tournament.status).lower()
    if status == "completed":
        return "status:completed"
    if status == "canceled":
        return "status:canceled"
    return f"round:{max(1, int(tournament.current_round))}:status:{status}"


def delivery_operation(existing_message_id: int | None) -> str:
    if existing_message_id is None:
        return "send"
    return f"edit:{int(existing_message_id)}"


def fallback_delivery_operation(existing_message_id: int) -> str:
    return f"fallback_send_after_edit:{int(existing_message_id)}"


def daily_cup_delivery_result(
    sent: int,
    edited: int,
    failed: int,
    skipped: int,
    new_message_ids: dict[int, int],
    replaced_message_ids: dict[int, int],
) -> dict[str, object]:
    return {
        "sent": sent,
        "edited": edited,
        "failed": failed,
        "skipped": skipped,
        "new_message_ids": new_message_ids,
        "replaced_message_ids": replaced_message_ids,
    }
