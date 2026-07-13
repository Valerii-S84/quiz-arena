from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.session import SessionLocal
from app.services.telegram_delivery import (
    SKIP_CODE_EDIT_REPLACED_BY_SEND,
    TelegramDeliveryFailure,
    TelegramDeliveryTarget,
    mark_telegram_delivery_failed,
    mark_telegram_delivery_failed_with_classification,
    record_telegram_delivery_skipped,
)


async def record_original_edit_skipped_after_fallback_skip(
    *,
    target: TelegramDeliveryTarget,
    happened_at: datetime,
    fallback_status: str,
) -> None:
    failure_reason = "fallback send skipped after edit failed"
    if fallback_status == "SENT":
        failure_reason = "edit delivery already replaced by fallback send"
    await record_telegram_delivery_skipped(
        target=target,
        happened_at=happened_at,
        failure_code=SKIP_CODE_EDIT_REPLACED_BY_SEND,
        failure_reason=failure_reason,
    )


async def record_original_edit_skipped_after_fallback_success(
    *,
    target: TelegramDeliveryTarget,
    happened_at: datetime,
) -> None:
    await record_telegram_delivery_skipped(
        target=target,
        happened_at=happened_at,
        failure_code=SKIP_CODE_EDIT_REPLACED_BY_SEND,
        failure_reason="edit delivery replaced by fallback send",
    )


async def mark_original_edit_failed_after_fallback_failure(
    *,
    idempotency_key: str,
    happened_at: datetime,
    failure: TelegramDeliveryFailure,
) -> None:
    await mark_telegram_delivery_failed_with_classification(
        idempotency_key=idempotency_key,
        happened_at=happened_at,
        failure=failure,
        failure_reason=f"fallback_send_failed_after_edit_failed:{failure.failure_reason}",
    )


async def mark_fallback_and_original_edit_failed(
    *,
    fallback_idempotency_key: str,
    original_idempotency_key: str,
    happened_at: datetime,
    exc: BaseException,
    session_local: Any = SessionLocal,
) -> TelegramDeliveryFailure:
    async with session_local.begin() as session:
        failure = await mark_telegram_delivery_failed(
            idempotency_key=fallback_idempotency_key,
            happened_at=happened_at,
            exc=exc,
            session=session,
        )
        await mark_telegram_delivery_failed_with_classification(
            idempotency_key=original_idempotency_key,
            happened_at=happened_at,
            failure=failure,
            failure_reason=(f"fallback_send_failed_after_edit_failed:{failure.failure_reason}"),
            session=session,
        )
    return failure


__all__ = [
    "mark_fallback_and_original_edit_failed",
    "mark_original_edit_failed_after_fallback_failure",
    "record_original_edit_skipped_after_fallback_skip",
    "record_original_edit_skipped_after_fallback_success",
]
