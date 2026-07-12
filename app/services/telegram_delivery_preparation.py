from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.repo.production_reliability_repo import TelegramDeliveryAttemptsRepo
from app.db.session import SessionLocal
from app.services.telegram_delivery_records import attempt_create, record_skipped
from app.services.telegram_delivery_retry import claim_controlled_retry
from app.services.telegram_delivery_types import (
    BLOCKED_CANDIDATE_TTL,
    FAILURE_CODE_BLOCKED,
    SKIP_CODE_NO_CHAT,
    DeliveryPreparation,
    TelegramDeliveryTarget,
)


async def prepare_telegram_delivery(
    *,
    target: TelegramDeliveryTarget,
    happened_at: datetime,
    session_local: Any = SessionLocal,
) -> DeliveryPreparation:
    if target.chat_id is None:
        return await record_skipped(
            target=target,
            happened_at=happened_at,
            failure_code=SKIP_CODE_NO_CHAT,
            failure_reason="target has no chat id",
            session_local=session_local,
            attempts_repo=TelegramDeliveryAttemptsRepo,
        )

    async with session_local.begin() as session:
        if (
            target.telegram_user_id is not None
            and await TelegramDeliveryAttemptsRepo.has_blocked_candidate(
                session,
                telegram_user_id=target.telegram_user_id,
                blocked_since=happened_at - BLOCKED_CANDIDATE_TTL,
            )
        ):
            attempt, created = await TelegramDeliveryAttemptsRepo.create_pending_once(
                session,
                item=attempt_create(target),
            )
            if created or attempt.status == "PENDING":
                updated = await TelegramDeliveryAttemptsRepo.mark_skipped(
                    session,
                    idempotency_key=target.idempotency_key,
                    skipped_at=happened_at,
                    failure_code=FAILURE_CODE_BLOCKED,
                    failure_reason="known blocked candidate",
                )
                _require_terminal_update(updated, "skipped")
            return DeliveryPreparation(
                idempotency_key=target.idempotency_key,
                should_send=False,
                status="SKIPPED",
                created=created,
            )

        attempt, created = await TelegramDeliveryAttemptsRepo.create_pending_once(
            session,
            item=attempt_create(target),
        )
        retry_claimed = False
        if created:
            should_send = True
        else:
            should_send, retry_claimed = await claim_controlled_retry(
                session,
                idempotency_key=target.idempotency_key,
                happened_at=happened_at,
                attempt=attempt,
                attempts_repo=TelegramDeliveryAttemptsRepo,
            )
        return DeliveryPreparation(
            idempotency_key=target.idempotency_key,
            should_send=should_send,
            status=str(attempt.status),
            created=created,
            retry_claimed=retry_claimed,
        )


def _require_terminal_update(updated: int, status: str) -> None:
    if updated != 1:
        raise RuntimeError(f"telegram delivery {status} terminal lease was lost")


__all__ = ["prepare_telegram_delivery"]
