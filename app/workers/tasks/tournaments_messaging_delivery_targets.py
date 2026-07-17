from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.repo.production_reliability_types import TelegramDeliveryAttemptCreate
from app.workers.tasks.tournaments_messaging_delivery_types import TournamentRoundDeliveryContext

SKIP_CODE_EDIT_REPLACED_BY_SEND = "EDIT_REPLACED_BY_FALLBACK_SEND"
SKIP_CODE_NO_CHAT = "MISSING_CHAT_ID"
PENDING_REPLAY_SAFE_CONTEXT_KEY = "pending_replay_safe"


@dataclass(frozen=True, slots=True)
class PrivateTournamentDeliveryTarget:
    attempt: TelegramDeliveryAttemptCreate
    chat_id: int | None

    @property
    def idempotency_key(self) -> str:
        return self.attempt.idempotency_key


def _build_delivery_idempotency_key(
    *,
    flow: str,
    correlation_id: str,
    target_type: str,
    target_id: str,
) -> str:
    return f"telegram-delivery:{flow}:{correlation_id}:{target_type}:{target_id}"


def private_round_delivery_target(
    *,
    delivery_context: TournamentRoundDeliveryContext,
    user_id: int,
    chat_id: int | None,
    delivery_operation: str,
    pending_replay_safe: bool,
) -> PrivateTournamentDeliveryTarget:
    context = delivery_context.request.context
    target_id = f"{user_id}:phase:{delivery_context.content_version}:{delivery_operation}"
    safe_context: dict[str, object] = {
        "tournament_id": delivery_context.correlation_id,
        "user_id": user_id,
        "status": str(context.tournament.status),
        "current_round": int(context.tournament.current_round),
        "content_version": delivery_context.content_version,
        PENDING_REPLAY_SAFE_CONTEXT_KEY: pending_replay_safe,
    }
    attempt = TelegramDeliveryAttemptCreate(
        flow=delivery_context.flow,
        task_name=delivery_context.task_name,
        correlation_id=delivery_context.correlation_id,
        idempotency_key=_build_delivery_idempotency_key(
            flow=delivery_context.flow,
            correlation_id=delivery_context.correlation_id,
            target_type="user",
            target_id=target_id,
        ),
        target_type="user",
        target_id=target_id,
        telegram_user_id=chat_id,
        safe_context=safe_context,
    )
    return PrivateTournamentDeliveryTarget(attempt=attempt, chat_id=chat_id)


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


__all__ = [
    "PrivateTournamentDeliveryTarget",
    "SKIP_CODE_EDIT_REPLACED_BY_SEND",
    "SKIP_CODE_NO_CHAT",
    "delivery_operation",
    "fallback_delivery_operation",
    "private_round_content_version",
    "private_round_delivery_target",
]
