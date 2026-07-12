from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.services.telegram_delivery_types import (
    FAILURE_CODE_FORBIDDEN,
    SKIP_CODE_EDIT_REPLACED_BY_SEND,
    TelegramDeliveryFailure,
    TelegramDeliveryTarget,
)
from app.workers.tasks import messaging_fallback_delivery

NOW_UTC = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def _edit_target() -> TelegramDeliveryTarget:
    return TelegramDeliveryTarget(
        flow="daily_cup_round_messaging",
        task_name="daily_cup.run_daily_cup_round_messaging",
        correlation_id="cup-1",
        target_type="user",
        target_id="1:phase:round:2:status:round_2:edit:222",
        idempotency_key="telegram-delivery:daily:cup-1:user:edit:222",
        telegram_user_id=101,
        chat_id=1001,
    )


@pytest.mark.asyncio
async def test_fallback_success_terminalizes_original_edit_row_as_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_attempt_row: dict[str, Any] = {
        "idempotency_key": _edit_target().idempotency_key,
        "status": "PENDING",
    }

    async def _record_skipped(**kwargs: Any) -> None:
        assert kwargs["target"].idempotency_key == original_attempt_row["idempotency_key"]
        original_attempt_row.update(
            {
                "status": "SKIPPED",
                "skipped_at": kwargs["happened_at"],
                "failure_code": kwargs["failure_code"],
                "failure_reason": kwargs["failure_reason"],
            }
        )

    monkeypatch.setattr(
        messaging_fallback_delivery,
        "record_telegram_delivery_skipped",
        _record_skipped,
    )

    await messaging_fallback_delivery.record_original_edit_skipped_after_fallback_success(
        target=_edit_target(),
        happened_at=NOW_UTC,
    )

    assert original_attempt_row == {
        "idempotency_key": _edit_target().idempotency_key,
        "status": "SKIPPED",
        "skipped_at": NOW_UTC,
        "failure_code": SKIP_CODE_EDIT_REPLACED_BY_SEND,
        "failure_reason": "edit delivery replaced by fallback send",
    }


@pytest.mark.asyncio
async def test_fallback_failure_terminalizes_original_edit_row_as_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_attempt_row: dict[str, Any] = {
        "idempotency_key": _edit_target().idempotency_key,
        "status": "PENDING",
    }
    fallback_failure = TelegramDeliveryFailure(
        failure_code=FAILURE_CODE_FORBIDDEN,
        failure_reason="bot blocked by user",
        telegram_error_code=403,
        is_blocked_candidate=True,
    )

    async def _mark_failed_with_classification(**kwargs: Any) -> None:
        assert kwargs["idempotency_key"] == original_attempt_row["idempotency_key"]
        original_attempt_row.update(
            {
                "status": "FAILED",
                "failed_at": kwargs["happened_at"],
                "failure_code": kwargs["failure"].failure_code,
                "failure_reason": kwargs["failure_reason"],
                "telegram_error_code": kwargs["failure"].telegram_error_code,
                "is_blocked_candidate": kwargs["failure"].is_blocked_candidate,
            }
        )

    monkeypatch.setattr(
        messaging_fallback_delivery,
        "mark_telegram_delivery_failed_with_classification",
        _mark_failed_with_classification,
    )

    await messaging_fallback_delivery.mark_original_edit_failed_after_fallback_failure(
        idempotency_key=_edit_target().idempotency_key,
        happened_at=NOW_UTC,
        failure=fallback_failure,
    )

    assert original_attempt_row == {
        "idempotency_key": _edit_target().idempotency_key,
        "status": "FAILED",
        "failed_at": NOW_UTC,
        "failure_code": FAILURE_CODE_FORBIDDEN,
        "failure_reason": "fallback_send_failed_after_edit_failed:bot blocked by user",
        "telegram_error_code": 403,
        "is_blocked_candidate": True,
    }
