from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.repo.production_reliability_repo import TelegramDeliveryAttemptsRepo
from app.db.session import SessionLocal
from app.services.telegram_delivery_types import (
    MAX_DELIVERY_ATTEMPTS,
    PENDING_REPLAY_SAFE_CONTEXT_KEY,
    STALE_PENDING_AFTER,
    TELEGRAM_DELIVERY_RETRY_POLICY,
    DeliveryPreparation,
)


async def claim_controlled_retry(
    session: Any,
    *,
    idempotency_key: str,
    happened_at: datetime,
    attempt: Any,
    attempts_repo: Any,
) -> tuple[bool, bool]:
    status = str(attempt.status)
    if status not in {"PENDING", "FAILED"}:
        return False, False
    replay_safe = pending_replay_safe(attempt)
    guaranteed_undelivered = (
        status == "FAILED"
        and getattr(attempt, "failure_code", None)
        in TELEGRAM_DELIVERY_RETRY_POLICY.guaranteed_undelivered_failure_codes
    )
    allow_stale_pending_retry = status == "PENDING" and replay_safe
    if not replay_safe and not guaranteed_undelivered:
        return False, False
    claimed = await attempts_repo.claim_retryable_attempt(
        session,
        idempotency_key=idempotency_key,
        claimed_at=happened_at,
        retry_policy=TELEGRAM_DELIVERY_RETRY_POLICY,
        stale_pending_before=happened_at - STALE_PENDING_AFTER,
        max_attempts=MAX_DELIVERY_ATTEMPTS,
        allow_stale_pending_retry=allow_stale_pending_retry,
    )
    return claimed > 0, status == "FAILED" and claimed > 0


async def begin_telegram_delivery_dispatch(
    delivery: DeliveryPreparation,
    *,
    happened_at: datetime,
    session_local: Any = SessionLocal,
    attempts_repo: Any = TelegramDeliveryAttemptsRepo,
) -> None:
    if not getattr(delivery, "retry_claimed", False):
        return
    async with session_local.begin() as session:
        updated = await attempts_repo.mark_retry_dispatched(
            session,
            idempotency_key=delivery.idempotency_key,
            claimed_at=happened_at,
            retry_policy=TELEGRAM_DELIVERY_RETRY_POLICY,
            max_attempts=MAX_DELIVERY_ATTEMPTS,
        )
        if updated != 1:
            raise RuntimeError("telegram delivery retry lease was lost")


def pending_replay_safe(attempt: Any) -> bool:
    safe_context = getattr(attempt, "safe_context", None)
    return (
        isinstance(safe_context, dict) and safe_context.get(PENDING_REPLAY_SAFE_CONTEXT_KEY) is True
    )
