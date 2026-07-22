from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramNotFound,
    TelegramRetryAfter,
    TelegramServerError,
)

from app.db.repo.production_reliability_types import TelegramDeliveryFailure

TelegramDeliveryOutcomeStatus = Literal["SENT", "SKIPPED", "FAILED", "RETRY"]

TELEGRAM_DELIVERY_TERMINAL_STATUSES = frozenset({"SENT", "SKIPPED", "FAILED"})


@dataclass(frozen=True, slots=True)
class TelegramDeliveryExceptionOutcome:
    status: Literal["FAILED", "RETRY"]
    failure: TelegramDeliveryFailure | None = None
    retry_after_seconds: int | None = None


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
                is_blocked_candidate=_looks_like_missing_chat(exc),
            ),
        )
    if isinstance(exc, TelegramNotFound):
        return TelegramDeliveryExceptionOutcome(
            status="FAILED",
            failure=TelegramDeliveryFailure(
                failure_code="TELEGRAM_NOT_FOUND",
                failure_reason=_failure_reason(exc),
                telegram_error_code=404,
                is_blocked_candidate=False,
            ),
        )
    if isinstance(exc, (TelegramNetworkError, TelegramServerError, TimeoutError, ConnectionError)):
        return TelegramDeliveryExceptionOutcome(
            status="FAILED",
            failure=TelegramDeliveryFailure(
                failure_code="TELEGRAM_TRANSIENT_SEND_ERROR",
                failure_reason=_failure_reason(exc),
                telegram_error_code=None,
                is_blocked_candidate=False,
            ),
        )
    return None


def terminal_replay_outcome(
    *,
    row: object,
    status: str,
    created: bool,
) -> TelegramDeliveryOutcome:
    return TelegramDeliveryOutcome(
        status=cast(TelegramDeliveryOutcomeStatus, status),
        created=created,
        attempted=False,
        replayed=not created,
        failure_code=getattr(row, "failure_code", None),
        failure_reason=getattr(row, "failure_reason", None),
        telegram_error_code=getattr(row, "telegram_error_code", None),
    )


def pending_replay_outcome(*, created: bool) -> TelegramDeliveryOutcome:
    return TelegramDeliveryOutcome(
        status="RETRY",
        created=created,
        attempted=False,
        replayed=not created,
        failure_code="PENDING_REPLAY",
    )


def skipped_outcome(
    *,
    created: bool,
    replayed: bool,
    skip: TelegramDeliverySkip,
) -> TelegramDeliveryOutcome:
    return TelegramDeliveryOutcome(
        status="SKIPPED",
        created=created,
        attempted=False,
        replayed=replayed,
        failure_code=skip.failure_code,
        failure_reason=skip.failure_reason,
    )


def _failure_reason(exc: Exception) -> str:
    return type(exc).__name__


def _looks_like_missing_chat(exc: Exception) -> bool:
    text = str(exc).lower()
    return "chat not found" in text or "bot was blocked" in text


__all__ = [
    "TELEGRAM_DELIVERY_TERMINAL_STATUSES",
    "TelegramDeliveryExceptionOutcome",
    "TelegramDeliveryOutcome",
    "TelegramDeliveryOutcomeStatus",
    "TelegramDeliverySkip",
    "classify_telegram_delivery_exception",
    "pending_replay_outcome",
    "skipped_outcome",
    "terminal_replay_outcome",
]
