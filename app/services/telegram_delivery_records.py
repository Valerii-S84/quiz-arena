from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.repo.production_reliability_repo import DeliveryAttemptCreate, hash_chat_id
from app.services.telegram_delivery_types import DeliveryPreparation, TelegramDeliveryTarget


async def record_skipped(
    *,
    target: TelegramDeliveryTarget,
    happened_at: datetime,
    failure_code: str,
    failure_reason: str,
    session_local: Any,
    attempts_repo: Any,
) -> DeliveryPreparation:
    async with session_local.begin() as session:
        attempt, created = await attempts_repo.create_pending_once(
            session,
            item=attempt_create(target),
        )
        if created or attempt.status == "PENDING":
            await attempts_repo.mark_skipped(
                session,
                idempotency_key=target.idempotency_key,
                skipped_at=happened_at,
                failure_code=failure_code,
                failure_reason=failure_reason,
            )
        return DeliveryPreparation(
            idempotency_key=target.idempotency_key,
            should_send=False,
            status="SKIPPED",
            created=created,
        )


def attempt_create(target: TelegramDeliveryTarget) -> DeliveryAttemptCreate:
    return DeliveryAttemptCreate(
        flow=target.flow,
        task_name=target.task_name,
        correlation_id=target.correlation_id,
        idempotency_key=target.idempotency_key,
        target_type=target.target_type,
        target_id=target.target_id,
        telegram_user_id=target.telegram_user_id,
        chat_id_hash=hash_chat_id(target.chat_id) if target.chat_id is not None else None,
        safe_context=target.safe_context,
    )
