from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from app.db.repo.production_reliability_types import TelegramDeliveryFailure

TelegramDeliveryOutcomeStatus = Literal["SENT", "SKIPPED", "FAILED", "RETRY"]

TELEGRAM_DELIVERY_TERMINAL_STATUSES = frozenset({"SENT", "SKIPPED", "FAILED"})


@dataclass(frozen=True, slots=True)
class TelegramDeliveryExceptionOutcome:
    status: Literal["FAILED", "RETRY"]
    failure: TelegramDeliveryFailure | None = None
    retry_after_seconds: int | None = None


def classify_telegram_delivery_exception(
    exc: Exception,
) -> TelegramDeliveryExceptionOutcome | None:
    if isinstance(exc, TelegramRetryAfter):
        return TelegramDeliveryExceptionOutcome(
            status="RETRY",
            retry_after_seconds=max(1, int(exc.retry_after)),
        )
    if isinstance(exc, TelegramForbiddenError):
        return TelegramDeliveryExceptionOutcome(
            status="FAILED",
            failure=TelegramDeliveryFailure(
                failure_code="TELEGRAM_FORBIDDEN",
                failure_reason=_failure_reason(exc),
                telegram_error_code=403,
                is_blocked_candidate=True,
            ),
        )
    if isinstance(exc, TelegramBadRequest):
        return TelegramDeliveryExceptionOutcome(
            status="FAILED",
            failure=TelegramDeliveryFailure(
                failure_code="TELEGRAM_BAD_REQUEST",
                failure_reason=_failure_reason(exc),
                telegram_error_code=400,
                is_blocked_candidate=False,
            ),
        )
    return None


def _failure_reason(exc: Exception) -> str:
    return str(exc)[:500]


__all__ = [
    "TELEGRAM_DELIVERY_TERMINAL_STATUSES",
    "TelegramDeliveryExceptionOutcome",
    "TelegramDeliveryOutcomeStatus",
    "classify_telegram_delivery_exception",
]
