from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.services import telegram_delivery as delivery
from tests.type_helpers import AsyncBeginContext

NOW_UTC = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


class _SessionLocal:
    def begin(self) -> AsyncBeginContext[str]:
        return AsyncBeginContext("session")


def _target(*, replay_safe: bool) -> delivery.TelegramDeliveryTarget:
    return delivery.TelegramDeliveryTarget(
        flow="daily_cup",
        task_name="task",
        correlation_id="cup-1",
        target_type="user",
        target_id="11",
        idempotency_key="delivery:cup-1:11",
        telegram_user_id=101,
        chat_id=101,
        safe_context={"pending_replay_safe": replay_safe},
    )


async def _prepare_failed_delivery(
    monkeypatch,
    *,
    replay_safe: bool,
    failure_code: str | None = None,
):
    captured: dict[str, object] = {}

    async def _has_blocked_candidate(_session, **_kwargs) -> bool:
        return False

    async def _create_pending_once(_session, *, item):
        return (
            SimpleNamespace(
                status="FAILED",
                failure_code=failure_code,
                safe_context={"pending_replay_safe": replay_safe},
            ),
            False,
        )

    async def _claim_retryable_attempt(_session, **kwargs) -> int:
        captured.update(kwargs)
        return 1

    monkeypatch.setattr(
        delivery.TelegramDeliveryAttemptsRepo,
        "has_blocked_candidate",
        _has_blocked_candidate,
    )
    monkeypatch.setattr(
        delivery.TelegramDeliveryAttemptsRepo,
        "create_pending_once",
        _create_pending_once,
    )
    monkeypatch.setattr(
        delivery.TelegramDeliveryAttemptsRepo,
        "claim_retryable_attempt",
        _claim_retryable_attempt,
    )
    result = await delivery.prepare_telegram_delivery(
        target=_target(replay_safe=replay_safe),
        happened_at=NOW_UTC,
        session_local=_SessionLocal(),
    )
    return result, captured


async def test_replay_safe_failed_delivery_allows_controlled_retry(monkeypatch) -> None:
    result, captured = await _prepare_failed_delivery(monkeypatch, replay_safe=True)

    assert result.should_send is True
    assert result.retry_claimed is True
    retry_policy = captured["retry_policy"]
    assert getattr(retry_policy, "retryable_failure_codes") == delivery.RETRYABLE_FAILURE_CODES
    assert captured["allow_stale_pending_retry"] is False


async def test_failed_send_without_confirmed_replay_safety_blocks_duplicate_send(
    monkeypatch,
) -> None:
    result, captured = await _prepare_failed_delivery(monkeypatch, replay_safe=False)

    assert result.should_send is False
    assert result.retry_claimed is False
    assert captured == {}


async def test_retry_after_failed_send_retries_without_replay_safe_flag(monkeypatch) -> None:
    result, captured = await _prepare_failed_delivery(
        monkeypatch,
        replay_safe=False,
        failure_code=delivery.FAILURE_CODE_RETRY_AFTER,
    )

    assert result.should_send is True
    assert result.retry_claimed is True
    retry_policy = captured["retry_policy"]
    assert getattr(retry_policy, "guaranteed_undelivered_failure_codes") == frozenset(
        {delivery.FAILURE_CODE_RETRY_AFTER}
    )


async def test_ambiguous_transient_failure_without_replay_safety_does_not_retry(
    monkeypatch,
) -> None:
    result, captured = await _prepare_failed_delivery(
        monkeypatch,
        replay_safe=False,
        failure_code=delivery.FAILURE_CODE_TRANSIENT,
    )

    assert result.should_send is False
    assert result.retry_claimed is False
    assert captured == {}
