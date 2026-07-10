from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from app.services.telegram_delivery_types import (
    FAILURE_CODE_BAD_REQUEST,
    FAILURE_CODE_FORBIDDEN,
    FAILURE_CODE_RETRY_AFTER,
    FAILURE_CODE_UNKNOWN,
    TelegramDeliveryFailure,
)


def classify_telegram_delivery_exception(exc: BaseException) -> TelegramDeliveryFailure:
    message = _safe_exception_label(exc)
    if isinstance(exc, TelegramForbiddenError):
        return TelegramDeliveryFailure(
            failure_code=FAILURE_CODE_FORBIDDEN,
            failure_reason=message,
            telegram_error_code=403,
            is_blocked_candidate=True,
        )
    if isinstance(exc, TelegramBadRequest):
        return TelegramDeliveryFailure(
            failure_code=FAILURE_CODE_BAD_REQUEST,
            failure_reason=message,
            telegram_error_code=400,
            is_blocked_candidate=_looks_like_missing_chat(exc),
        )
    if isinstance(exc, TelegramRetryAfter):
        return TelegramDeliveryFailure(
            failure_code=FAILURE_CODE_RETRY_AFTER,
            failure_reason=message,
            telegram_error_code=429,
            is_blocked_candidate=False,
        )
    return TelegramDeliveryFailure(
        failure_code=FAILURE_CODE_UNKNOWN,
        failure_reason=message,
        telegram_error_code=None,
        is_blocked_candidate=False,
    )


def _safe_exception_label(exc: BaseException) -> str:
    return type(exc).__name__


def _looks_like_missing_chat(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "chat not found" in text or "bot was blocked" in text
