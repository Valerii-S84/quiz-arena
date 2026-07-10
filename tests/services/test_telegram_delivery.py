from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from app.db.repo.production_reliability_repo import DeliveryAttemptCreate, hash_chat_id
from app.services import telegram_delivery as delivery
from tests.type_helpers import AsyncBeginContext

NOW_UTC = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


class _SessionLocal:
    def begin(self) -> AsyncBeginContext[str]:
        return AsyncBeginContext("session")


def _target(*, pending_replay_safe: bool = False) -> delivery.TelegramDeliveryTarget:
    return delivery.TelegramDeliveryTarget(
        flow="daily_cup",
        task_name="task",
        correlation_id="cup-1",
        target_type="user",
        target_id="11",
        idempotency_key="delivery:cup-1:11",
        telegram_user_id=101,
        chat_id=101,
        safe_context={"user_id": 11, "pending_replay_safe": pending_replay_safe},
    )


async def test_prepare_delivery_creates_pending_with_chat_hash(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def _has_blocked_candidate(_session, **_kwargs) -> bool:
        return False

    async def _create_pending_once(_session, *, item):
        captured["item"] = item
        return SimpleNamespace(status="PENDING"), True

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

    result = await delivery.prepare_telegram_delivery(
        target=_target(),
        happened_at=NOW_UTC,
        session_local=_SessionLocal(),
    )

    item = cast(DeliveryAttemptCreate, captured["item"])
    assert result.should_send is True
    assert item.chat_id_hash == hash_chat_id(101)
    assert item.target_id == "11"


async def test_prepare_delivery_skips_known_blocked_candidate(monkeypatch) -> None:
    skipped: list[dict[str, object]] = []
    blocked_lookup: dict[str, object] = {}

    async def _has_blocked_candidate(_session, **kwargs) -> bool:
        blocked_lookup.update(kwargs)
        return True

    async def _create_pending_once(_session, *, item):
        return SimpleNamespace(status="PENDING"), True

    async def _mark_skipped(_session, **kwargs) -> int:
        skipped.append(kwargs)
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
    monkeypatch.setattr(delivery.TelegramDeliveryAttemptsRepo, "mark_skipped", _mark_skipped)

    result = await delivery.prepare_telegram_delivery(
        target=_target(),
        happened_at=NOW_UTC,
        session_local=_SessionLocal(),
    )

    assert result.should_send is False
    assert blocked_lookup["blocked_since"] == NOW_UTC - delivery.BLOCKED_CANDIDATE_TTL
    assert skipped[0]["failure_code"] == delivery.FAILURE_CODE_BLOCKED


async def test_existing_sent_delivery_blocks_duplicate_send(monkeypatch) -> None:
    async def _has_blocked_candidate(_session, **_kwargs) -> bool:
        return False

    async def _create_pending_once(_session, *, item):
        return SimpleNamespace(status="SENT"), False

    async def _claim_retryable_attempt(_session, **_kwargs) -> int:
        raise AssertionError("SENT delivery must not be retried")

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
        target=_target(),
        happened_at=NOW_UTC,
        session_local=_SessionLocal(),
    )

    assert result.should_send is False


async def test_fresh_pending_delivery_blocks_duplicate_send(monkeypatch) -> None:
    async def _has_blocked_candidate(_session, **_kwargs) -> bool:
        return False

    async def _create_pending_once(_session, *, item):
        return SimpleNamespace(status="PENDING", safe_context={"pending_replay_safe": True}), False

    async def _claim_retryable_attempt(_session, **_kwargs) -> int:
        return 0

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
        target=_target(),
        happened_at=NOW_UTC,
        session_local=_SessionLocal(),
    )

    assert result.should_send is False


async def test_stale_pending_delivery_allows_controlled_retry(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def _has_blocked_candidate(_session, **_kwargs) -> bool:
        return False

    async def _create_pending_once(_session, *, item):
        return SimpleNamespace(status="PENDING", safe_context={"pending_replay_safe": True}), False

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
        target=_target(pending_replay_safe=True),
        happened_at=NOW_UTC,
        session_local=_SessionLocal(),
    )

    assert result.should_send is True
    assert captured["stale_pending_before"] == NOW_UTC - delivery.STALE_PENDING_AFTER
    assert captured["max_attempts"] == delivery.MAX_DELIVERY_ATTEMPTS
    assert captured["allow_stale_pending_retry"] is True


async def test_stale_pending_send_delivery_without_safe_context_does_not_retry(monkeypatch) -> None:
    async def _has_blocked_candidate(_session, **_kwargs) -> bool:
        return False

    async def _create_pending_once(_session, *, item):
        return SimpleNamespace(status="PENDING", safe_context={"pending_replay_safe": False}), False

    async def _claim_retryable_attempt(_session, **_kwargs) -> int:
        raise AssertionError("unsafe stale PENDING send must not be claimed")

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
        target=_target(),
        happened_at=NOW_UTC,
        session_local=_SessionLocal(),
    )

    assert result.should_send is False


async def test_retryable_failed_delivery_allows_controlled_retry(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def _has_blocked_candidate(_session, **_kwargs) -> bool:
        return False

    async def _create_pending_once(_session, *, item):
        return SimpleNamespace(status="FAILED"), False

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
        target=_target(),
        happened_at=NOW_UTC,
        session_local=_SessionLocal(),
    )

    assert result.should_send is True
    assert captured["retryable_failure_codes"] == delivery.RETRYABLE_FAILURE_CODES
    assert captured["allow_stale_pending_retry"] is False


async def test_nonretryable_failed_delivery_does_not_retry(monkeypatch) -> None:
    async def _has_blocked_candidate(_session, **_kwargs) -> bool:
        return False

    async def _create_pending_once(_session, *, item):
        return SimpleNamespace(status="FAILED"), False

    async def _claim_retryable_attempt(_session, **_kwargs) -> int:
        return 0

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
        target=_target(),
        happened_at=NOW_UTC,
        session_local=_SessionLocal(),
    )

    assert result.should_send is False


async def test_skipped_delivery_does_not_retry(monkeypatch) -> None:
    async def _has_blocked_candidate(_session, **_kwargs) -> bool:
        return False

    async def _create_pending_once(_session, *, item):
        return SimpleNamespace(status="SKIPPED"), False

    async def _claim_retryable_attempt(_session, **_kwargs) -> int:
        raise AssertionError("SKIPPED delivery must not be retried")

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
        target=_target(),
        happened_at=NOW_UTC,
        session_local=_SessionLocal(),
    )

    assert result.should_send is False


def test_forbidden_error_is_blocked_candidate() -> None:
    exc = TelegramForbiddenError(
        method=SendMessage(chat_id=101, text="x"),
        message="Forbidden: bot was blocked by the user",
    )

    result = delivery.classify_telegram_delivery_exception(exc)

    assert result.failure_code == delivery.FAILURE_CODE_FORBIDDEN
    assert result.telegram_error_code == 403
    assert result.is_blocked_candidate is True


def test_generic_error_is_not_blocked_candidate() -> None:
    result = delivery.classify_telegram_delivery_exception(RuntimeError("boom"))

    assert result.failure_code == delivery.FAILURE_CODE_UNKNOWN
    assert result.telegram_error_code is None
    assert result.is_blocked_candidate is False
