from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import SendMessage

from app.workers.tasks import tournaments_message_delivery_persistence


class _SessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_args: object) -> None:
        return None


class _SessionLocal:
    @staticmethod
    def begin() -> _SessionContext:
        return _SessionContext()


def _delivery_target(*, pending_replay_safe: bool, chat_id: int | None = 101) -> Any:
    return SimpleNamespace(
        attempt=SimpleNamespace(idempotency_key="private"),
        chat_id=chat_id,
        pending_replay_safe=pending_replay_safe,
        idempotency_key="private",
    )


async def test_private_prepare_claims_stale_pending_replay_safe_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim_calls: list[dict[str, object]] = []

    async def _create_once(_session: object, *, attempt: object) -> tuple[object, bool]:
        return SimpleNamespace(status="PENDING"), False

    async def _claim_stale(_session: object, **kwargs: object) -> bool:
        claim_calls.append(kwargs)
        return True

    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TelegramDeliveryAttemptsRepo,
        "create_once",
        _create_once,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TelegramDeliveryAttemptsRepo,
        "claim_stale_pending_replay",
        _claim_stale,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence,
        "SessionLocal",
        _SessionLocal,
    )

    prepared = await tournaments_message_delivery_persistence.prepare_private_tournament_delivery(
        _delivery_target(pending_replay_safe=True),
    )

    assert prepared.should_send is True
    assert prepared.status == "RETRY"
    assert prepared.created is False
    assert claim_calls == [{"idempotency_key": "private", "claim_ttl_seconds": 300}]


async def test_private_prepare_keeps_fresh_pending_replay_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim_calls: list[dict[str, object]] = []

    async def _create_once(_session: object, *, attempt: object) -> tuple[object, bool]:
        return SimpleNamespace(status="PENDING", updated_at=datetime.now(UTC)), False

    async def _claim_stale(_session: object, **kwargs: object) -> bool:
        claim_calls.append(kwargs)
        return False

    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TelegramDeliveryAttemptsRepo,
        "create_once",
        _create_once,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TelegramDeliveryAttemptsRepo,
        "claim_stale_pending_replay",
        _claim_stale,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence,
        "SessionLocal",
        _SessionLocal,
    )

    prepared = await tournaments_message_delivery_persistence.prepare_private_tournament_delivery(
        _delivery_target(pending_replay_safe=True),
    )

    assert prepared.should_send is False
    assert prepared.status == "RETRY"
    assert prepared.created is False
    assert prepared.retry_after_seconds in {299, 300}
    assert claim_calls == [{"idempotency_key": "private", "claim_ttl_seconds": 300}]


async def test_private_prepare_does_not_claim_unsafe_pending_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim_calls: list[dict[str, object]] = []

    async def _create_once(_session: object, *, attempt: object) -> tuple[object, bool]:
        return SimpleNamespace(status="PENDING"), False

    async def _claim_stale(_session: object, **kwargs: object) -> bool:
        claim_calls.append(kwargs)
        return True

    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TelegramDeliveryAttemptsRepo,
        "create_once",
        _create_once,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TelegramDeliveryAttemptsRepo,
        "claim_stale_pending_replay",
        _claim_stale,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence,
        "SessionLocal",
        _SessionLocal,
    )

    prepared = await tournaments_message_delivery_persistence.prepare_private_tournament_delivery(
        _delivery_target(pending_replay_safe=False),
    )

    assert prepared.should_send is False
    assert prepared.status == "RETRY"
    assert prepared.created is False
    assert claim_calls == []


async def test_private_retryable_failure_stays_pending_and_deferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = SimpleNamespace(failure_code=None, failure_reason=None)
    deferred_calls: list[dict[str, object]] = []

    async def _get_by_idempotency_key(*_args: object, **_kwargs: object) -> object:
        return row

    async def _defer_retry_after(*_args: object, **kwargs: object) -> bool:
        deferred_calls.append(kwargs)
        return True

    repo = tournaments_message_delivery_persistence.TelegramDeliveryAttemptsRepo
    monkeypatch.setattr(repo, "get_by_idempotency_key", _get_by_idempotency_key)
    monkeypatch.setattr(repo, "defer_retry_after", _defer_retry_after)
    monkeypatch.setattr(tournaments_message_delivery_persistence, "SessionLocal", _SessionLocal)

    result = (
        await tournaments_message_delivery_persistence.record_private_tournament_delivery_failure(
            _delivery_target(pending_replay_safe=False),
            TelegramRetryAfter(
                method=SendMessage(chat_id=101, text="round"),
                message="flood",
                retry_after=7,
            ),
        )
    )

    assert result.status == "RETRY"
    assert result.retry_after_seconds == 7
    assert row.failure_code == "TELEGRAM_RETRY_NEEDED"
    assert deferred_calls == [
        {
            "idempotency_key": "private",
            "retry_after_seconds": 7,
            "claim_ttl_seconds": 300,
        }
    ]


async def test_private_prepare_claims_deferred_retry_for_unsafe_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = SimpleNamespace(
        status="PENDING",
        failure_code="TELEGRAM_RETRY_NEEDED",
        failure_reason="retry",
    )

    async def _create_once(*_args: object, **_kwargs: object) -> tuple[object, bool]:
        return row, False

    async def _claim_stale(*_args: object, **_kwargs: object) -> bool:
        return True

    repo = tournaments_message_delivery_persistence.TelegramDeliveryAttemptsRepo
    monkeypatch.setattr(repo, "create_once", _create_once)
    monkeypatch.setattr(repo, "claim_stale_pending_replay", _claim_stale)
    monkeypatch.setattr(tournaments_message_delivery_persistence, "SessionLocal", _SessionLocal)

    prepared = await tournaments_message_delivery_persistence.prepare_private_tournament_delivery(
        _delivery_target(pending_replay_safe=False)
    )

    assert prepared.should_send is True
    assert row.failure_code is None
    assert row.failure_reason is None
