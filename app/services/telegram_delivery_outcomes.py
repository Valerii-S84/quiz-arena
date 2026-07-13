from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.repo.production_reliability_repo import TelegramDeliveryAttemptsRepo
from app.db.session import SessionLocal
from app.services.telegram_delivery_errors import classify_telegram_delivery_exception
from app.services.telegram_delivery_records import record_skipped
from app.services.telegram_delivery_types import (
    DeliveryPreparation,
    TelegramDeliveryFailure,
    TelegramDeliveryTarget,
)


async def mark_telegram_delivery_sent(
    *,
    idempotency_key: str,
    happened_at: datetime,
    session_local: Any = SessionLocal,
    session: Any | None = None,
) -> None:
    if session is not None:
        await _mark_telegram_delivery_sent(
            session,
            idempotency_key=idempotency_key,
            happened_at=happened_at,
        )
        return
    async with session_local.begin() as session:
        await _mark_telegram_delivery_sent(
            session,
            idempotency_key=idempotency_key,
            happened_at=happened_at,
        )


async def _mark_telegram_delivery_sent(
    session: Any,
    *,
    idempotency_key: str,
    happened_at: datetime,
) -> None:
    updated = await TelegramDeliveryAttemptsRepo.mark_sent(
        session,
        idempotency_key=idempotency_key,
        sent_at=happened_at,
    )
    _require_terminal_update(updated, "sent")


async def mark_telegram_delivery_failed(
    *,
    idempotency_key: str,
    happened_at: datetime,
    exc: BaseException,
    session_local: Any = SessionLocal,
) -> TelegramDeliveryFailure:
    failure = classify_telegram_delivery_exception(exc)
    async with session_local.begin() as session:
        updated = await TelegramDeliveryAttemptsRepo.mark_failed(
            session,
            idempotency_key=idempotency_key,
            failed_at=happened_at,
            failure_code=failure.failure_code,
            failure_reason=failure.failure_reason,
            telegram_error_code=failure.telegram_error_code,
            is_blocked_candidate=failure.is_blocked_candidate,
        )
        _require_terminal_update(updated, "failed")
    return failure


async def mark_telegram_delivery_failed_with_classification(
    *,
    idempotency_key: str,
    happened_at: datetime,
    failure: TelegramDeliveryFailure,
    failure_reason: str,
    session_local: Any = SessionLocal,
) -> None:
    async with session_local.begin() as session:
        updated = await TelegramDeliveryAttemptsRepo.mark_failed(
            session,
            idempotency_key=idempotency_key,
            failed_at=happened_at,
            failure_code=failure.failure_code,
            failure_reason=failure_reason,
            telegram_error_code=failure.telegram_error_code,
            is_blocked_candidate=failure.is_blocked_candidate,
        )
        _require_terminal_update(updated, "failed")


def _require_terminal_update(updated: int, status: str) -> None:
    if updated != 1:
        raise RuntimeError(f"telegram delivery {status} terminal lease was lost")


async def record_telegram_delivery_skipped(
    *,
    target: TelegramDeliveryTarget,
    happened_at: datetime,
    failure_code: str,
    failure_reason: str,
    session_local: Any = SessionLocal,
) -> DeliveryPreparation:
    return await record_skipped(
        target=target,
        happened_at=happened_at,
        failure_code=failure_code,
        failure_reason=failure_reason,
        session_local=session_local,
        attempts_repo=TelegramDeliveryAttemptsRepo,
    )


__all__ = [
    "mark_telegram_delivery_failed",
    "mark_telegram_delivery_failed_with_classification",
    "mark_telegram_delivery_sent",
    "record_telegram_delivery_skipped",
]
