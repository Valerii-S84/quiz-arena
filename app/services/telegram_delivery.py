from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.production_reliability_types import TelegramDeliveryAttemptCreate
from app.db.repo.telegram_delivery_attempts_repo import TelegramDeliveryAttemptsRepo
from app.db.repo.telegram_delivery_retry_repo import TelegramDeliveryRetryRepo
from app.services.telegram_delivery_outcomes import (
    TELEGRAM_DELIVERY_TERMINAL_STATUSES,
    TelegramDeliveryOutcomeStatus,
    classify_telegram_delivery_exception,
)

TelegramDeliverySend = Callable[[], Awaitable[object]]


@dataclass(frozen=True, slots=True)
class TelegramDeliverySkip:
    failure_code: str
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class TelegramDeliveryOutcome:
    status: TelegramDeliveryOutcomeStatus
    created: bool
    attempted: bool
    replayed: bool = False
    failure_code: str | None = None
    failure_reason: str | None = None
    telegram_error_code: int | None = None
    retry_after_seconds: int | None = None


async def deliver_telegram_once(
    session: AsyncSession,
    *,
    attempt: TelegramDeliveryAttemptCreate,
    send: TelegramDeliverySend,
    skip: TelegramDeliverySkip | None = None,
    attempts_repo: Any = TelegramDeliveryAttemptsRepo,
) -> TelegramDeliveryOutcome:
    row, created = await attempts_repo.create_once(session, attempt=attempt)
    current_status = str(getattr(row, "status", "PENDING"))
    replayed = not created

    if current_status in TELEGRAM_DELIVERY_TERMINAL_STATUSES:
        return TelegramDeliveryOutcome(
            status=cast(TelegramDeliveryOutcomeStatus, current_status),
            created=created,
            attempted=False,
            replayed=replayed,
        )

    if skip is not None:
        await attempts_repo.mark_skipped(
            session,
            idempotency_key=attempt.idempotency_key,
            failure_code=skip.failure_code,
            failure_reason=skip.failure_reason,
        )
        return TelegramDeliveryOutcome(
            status="SKIPPED",
            created=created,
            attempted=False,
            replayed=replayed,
            failure_code=skip.failure_code,
            failure_reason=skip.failure_reason,
        )

    try:
        await send()
    except Exception as exc:
        classified = classify_telegram_delivery_exception(exc)
        if classified is None:
            raise
        if classified.status == "RETRY":
            return TelegramDeliveryOutcome(
                status="RETRY",
                created=created,
                attempted=True,
                replayed=replayed,
                retry_after_seconds=classified.retry_after_seconds,
            )
        if classified.failure is None:
            raise

        await attempts_repo.mark_failed(
            session,
            idempotency_key=attempt.idempotency_key,
            failure=classified.failure,
        )
        return TelegramDeliveryOutcome(
            status="FAILED",
            created=created,
            attempted=True,
            replayed=replayed,
            failure_code=classified.failure.failure_code,
            failure_reason=classified.failure.failure_reason,
            telegram_error_code=classified.failure.telegram_error_code,
        )

    await attempts_repo.mark_sent(session, idempotency_key=attempt.idempotency_key)
    return TelegramDeliveryOutcome(
        status="SENT",
        created=created,
        attempted=True,
        replayed=replayed,
    )


async def claim_telegram_delivery_retries(
    session: AsyncSession,
    *,
    flow: str,
    limit: int,
    claim_ttl_seconds: int = 300,
    retry_repo: Any = TelegramDeliveryRetryRepo,
) -> list[object]:
    return await retry_repo.claim_pending_batch(
        session,
        flow=flow,
        limit=limit,
        claim_ttl_seconds=claim_ttl_seconds,
    )


__all__ = [
    "TelegramDeliveryOutcome",
    "TelegramDeliverySend",
    "TelegramDeliverySkip",
    "claim_telegram_delivery_retries",
    "deliver_telegram_once",
]
