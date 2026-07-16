from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage

from app.services.telegram_delivery_outcomes import classify_telegram_delivery_exception


def test_classify_telegram_forbidden_as_blocked_candidate() -> None:
    outcome = classify_telegram_delivery_exception(
        TelegramForbiddenError(
            method=SendMessage(chat_id=101, text="x"),
            message="bot was blocked by the user",
        )
    )

    assert outcome is not None
    assert outcome.status == "FAILED"
    assert outcome.failure is not None
    assert outcome.failure.failure_code == "TELEGRAM_FORBIDDEN"
    assert outcome.failure.telegram_error_code == 403
    assert outcome.failure.is_blocked_candidate is True


def test_classify_telegram_bad_request_as_non_blocked_failure() -> None:
    outcome = classify_telegram_delivery_exception(
        TelegramBadRequest(
            method=SendMessage(chat_id=101, text="x"),
            message="chat not found",
        )
    )

    assert outcome is not None
    assert outcome.status == "FAILED"
    assert outcome.failure is not None
    assert outcome.failure.failure_code == "TELEGRAM_BAD_REQUEST"
    assert outcome.failure.telegram_error_code == 400
    assert outcome.failure.is_blocked_candidate is False


def test_classify_telegram_retry_after_as_retryable_outcome() -> None:
    outcome = classify_telegram_delivery_exception(
        TelegramRetryAfter(
            method=SendMessage(chat_id=101, text="x"),
            message="flood",
            retry_after=9,
        )
    )

    assert outcome is not None
    assert outcome.status == "RETRY"
    assert outcome.retry_after_seconds == 9
    assert outcome.failure is None


def test_unclassified_exception_is_left_to_caller_retry_semantics() -> None:
    assert classify_telegram_delivery_exception(RuntimeError("network maybe sent")) is None
