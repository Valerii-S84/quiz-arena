from __future__ import annotations

import inspect
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest

from app.services.telegram_delivery_retry import (
    begin_telegram_delivery_dispatch,
    claim_controlled_retry,
)
from app.services.telegram_delivery_types import DeliveryPreparation
from app.workers.tasks import (
    arena_duels_notification_delivery,
    daily_cup_cancel_delivery,
    daily_cup_message_delivery_persistence,
    daily_cup_messaging_delivery_runtime,
    daily_cup_messaging_delivery_steps,
    daily_cup_registration_push,
    daily_cup_turn_reminder_delivery_runtime,
    tournaments_messaging_delivery_runtime,
    tournaments_messaging_delivery_steps,
)

NOW_UTC = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)


class RetryRepo:
    claim_result = 1
    dispatch_result = 1
    claim_kwargs: dict[str, object] = {}
    dispatch_kwargs: dict[str, object] = {}

    @classmethod
    async def claim_retryable_attempt(cls, _session, **kwargs) -> int:
        cls.claim_kwargs = kwargs
        return cls.claim_result

    @classmethod
    async def mark_retry_dispatched(cls, _session, **kwargs) -> int:
        cls.dispatch_kwargs = kwargs
        return cls.dispatch_result


class SessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_args) -> None:
        return None


class SessionLocal:
    @staticmethod
    def begin() -> SessionContext:
        return SessionContext()


async def test_failed_attempt_claim_stays_leased_until_dispatch() -> None:
    RetryRepo.claim_result = 1

    should_send, retry_claimed = await claim_controlled_retry(
        object(),
        idempotency_key="delivery:retry",
        happened_at=NOW_UTC,
        attempt=SimpleNamespace(
            status="FAILED",
            safe_context={"pending_replay_safe": True},
        ),
        attempts_repo=RetryRepo,
    )

    assert should_send is True
    assert retry_claimed is True
    assert RetryRepo.claim_kwargs["claimed_at"] == NOW_UTC
    assert RetryRepo.claim_kwargs["stale_pending_before"] == NOW_UTC - timedelta(minutes=15)


async def test_dispatch_transitions_exact_claimed_retry() -> None:
    RetryRepo.dispatch_result = 1
    delivery = DeliveryPreparation("delivery:retry", True, "FAILED", False, True)

    await begin_telegram_delivery_dispatch(
        delivery,
        happened_at=NOW_UTC,
        session_local=SessionLocal,
        attempts_repo=RetryRepo,
    )

    assert RetryRepo.dispatch_kwargs["idempotency_key"] == "delivery:retry"
    assert RetryRepo.dispatch_kwargs["claimed_at"] == NOW_UTC


async def test_dispatch_blocks_send_when_retry_lease_was_lost() -> None:
    RetryRepo.dispatch_result = 0
    delivery = DeliveryPreparation("delivery:retry", True, "FAILED", False, True)

    with pytest.raises(RuntimeError, match="retry lease was lost"):
        await begin_telegram_delivery_dispatch(
            delivery,
            happened_at=NOW_UTC,
            session_local=SessionLocal,
            attempts_repo=RetryRepo,
        )


async def test_new_delivery_does_not_need_retry_dispatch() -> None:
    RetryRepo.dispatch_kwargs = {}
    delivery = DeliveryPreparation("delivery:new", True, "PENDING", True)

    await begin_telegram_delivery_dispatch(
        delivery,
        happened_at=NOW_UTC,
        session_local=SessionLocal,
        attempts_repo=RetryRepo,
    )

    assert RetryRepo.dispatch_kwargs == {}


@pytest.mark.parametrize(
    ("source_modules", "prepare_pattern", "dispatch_pattern", "expected_paths"),
    [
        pytest.param(
            (arena_duels_notification_delivery,),
            r"prepare_telegram_delivery\(",
            r"begin_telegram_delivery_dispatch\(",
            1,
            id="arena-duels",
        ),
        pytest.param(
            (daily_cup_cancel_delivery,),
            r"operations\.prepare_delivery\(",
            r"operations\.begin_dispatch\(",
            1,
            id="daily-cup-cancel",
        ),
        pytest.param(
            (daily_cup_messaging_delivery_runtime, daily_cup_messaging_delivery_steps),
            r"dependencies\.prepare_telegram_delivery\(",
            r"dependencies\.begin_telegram_delivery_dispatch\(",
            2,
            id="daily-cup-messaging",
        ),
        pytest.param(
            (daily_cup_registration_push,),
            r"prepare_telegram_delivery\(",
            r"begin_telegram_delivery_dispatch\(",
            1,
            id="daily-cup-registration",
        ),
        pytest.param(
            (daily_cup_turn_reminder_delivery_runtime,),
            r"dependencies\.prepare_telegram_delivery\(",
            r"dependencies\.begin_telegram_delivery_dispatch\(",
            1,
            id="daily-cup-turn-reminder",
        ),
        pytest.param(
            (tournaments_messaging_delivery_runtime, tournaments_messaging_delivery_steps),
            r"operations\.prepare(?:_fallback)?_delivery\(",
            r"operations\.begin(?:_fallback)?_dispatch\(",
            2,
            id="tournaments-messaging",
        ),
    ],
)
def test_each_delivery_prepare_path_has_a_later_dispatch_gate(
    source_modules: tuple[Any, ...],
    prepare_pattern: str,
    dispatch_pattern: str,
    expected_paths: int,
) -> None:
    path_count = 0
    for module in source_modules:
        source = inspect.getsource(module)
        prepares = [match.start() for match in re.finditer(prepare_pattern, source)]
        dispatches = [match.start() for match in re.finditer(dispatch_pattern, source)]

        assert len(prepares) == len(dispatches) == 1
        assert all(
            prepare < dispatch for prepare, dispatch in zip(prepares, dispatches, strict=True)
        )
        path_count += len(prepares)

    assert path_count == expected_paths


async def test_daily_cup_fallback_persists_replacement_before_sent(monkeypatch) -> None:
    calls: list[str] = []
    persisted: dict[str, object] = {}

    async def _persist(**kwargs) -> None:
        persisted.update(kwargs)
        calls.append("persist")

    async def _sent(*_args, **_kwargs) -> int:
        calls.append("sent")
        return 1

    async def _skipped(*_args, **_kwargs) -> int:
        calls.append("skipped")
        return 1

    monkeypatch.setattr(
        daily_cup_message_delivery_persistence,
        "persist_standings_message_ids",
        _persist,
    )
    monkeypatch.setattr(
        daily_cup_message_delivery_persistence.TelegramDeliveryAttemptsRepo,
        "mark_sent",
        _sent,
    )
    monkeypatch.setattr(
        daily_cup_message_delivery_persistence.TelegramDeliveryAttemptsRepo,
        "mark_skipped",
        _skipped,
    )
    monkeypatch.setattr(daily_cup_message_delivery_persistence, "SessionLocal", SessionLocal)
    await daily_cup_message_delivery_persistence.persist_daily_cup_sent_message(
        cast(Any, SimpleNamespace(idempotency_key="fallback")),
        UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        1,
        SimpleNamespace(message_id=501),
        NOW_UTC,
        replace_existing=True,
        original_target=cast(Any, SimpleNamespace(idempotency_key="original-edit")),
    )

    assert persisted["new_message_ids"] == {}
    assert persisted["replaced_message_ids"] == {1: 501}
    assert calls == ["persist", "sent", "skipped"]
