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
    daily_cup_core,
    daily_cup_message_delivery_persistence,
    daily_cup_messaging_delivery,
    daily_cup_registration_push,
    daily_cup_turn_reminder_delivery,
    tournaments_message_delivery_persistence,
    tournaments_messaging_delivery,
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
        attempt=SimpleNamespace(status="FAILED", safe_context={}),
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
    ("module", "expected_paths"),
    [
        (arena_duels_notification_delivery, 1),
        (daily_cup_core, 1),
        (daily_cup_messaging_delivery, 2),
        (daily_cup_registration_push, 1),
        (daily_cup_turn_reminder_delivery, 1),
        (tournaments_messaging_delivery, 2),
    ],
)
def test_each_delivery_prepare_path_has_a_later_dispatch_gate(
    module: Any, expected_paths: int
) -> None:
    source = inspect.getsource(module)
    prepares = [match.start() for match in re.finditer(r"prepare_telegram_delivery\(", source)]
    dispatches = [
        match.start() for match in re.finditer(r"begin_telegram_delivery_dispatch\(", source)
    ]

    assert len(prepares) == len(dispatches) == expected_paths
    assert all(prepare < dispatch for prepare, dispatch in zip(prepares, dispatches, strict=True))


async def test_daily_cup_fallback_persists_replacement_before_sent(monkeypatch) -> None:
    calls: list[str] = []
    persisted: dict[str, object] = {}

    async def _persist(**kwargs) -> None:
        persisted.update(kwargs)
        calls.append("persist")

    async def _sent(*_args, **_kwargs) -> int:
        calls.append("sent")
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
    monkeypatch.setattr(daily_cup_message_delivery_persistence, "SessionLocal", SessionLocal)
    await daily_cup_message_delivery_persistence.persist_daily_cup_sent_message(
        cast(Any, SimpleNamespace(idempotency_key="fallback")),
        UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        1,
        SimpleNamespace(message_id=501),
        NOW_UTC,
        replace_existing=True,
    )

    assert persisted["new_message_ids"] == {}
    assert persisted["replaced_message_ids"] == {1: 501}
    assert calls == ["persist", "sent"]


@pytest.mark.parametrize("replace_existing", [False, True])
async def test_private_message_id_persists_before_terminal_sent(
    monkeypatch, replace_existing: bool
) -> None:
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
        tournaments_message_delivery_persistence, "persist_standings_message_ids", _persist
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TelegramDeliveryAttemptsRepo,
        "mark_sent",
        _sent,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TelegramDeliveryAttemptsRepo,
        "mark_skipped",
        _skipped,
    )
    monkeypatch.setattr(tournaments_message_delivery_persistence, "SessionLocal", SessionLocal)
    await tournaments_message_delivery_persistence.persist_private_tournament_sent_message(
        cast(Any, SimpleNamespace(idempotency_key="private")),
        UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        2,
        SimpleNamespace(message_id=502),
        NOW_UTC,
        replace_existing=replace_existing,
        original_target=(
            cast(Any, SimpleNamespace(idempotency_key="original")) if replace_existing else None
        ),
    )

    assert persisted["new_message_ids"] == ({} if replace_existing else {2: 502})
    assert persisted["replaced_message_ids"] == ({2: 502} if replace_existing else {})
    assert calls == (["persist", "sent", "skipped"] if replace_existing else ["persist", "sent"])


def test_private_delivery_uses_persistence_helper_for_initial_and_fallback_sends() -> None:
    source = inspect.getsource(tournaments_messaging_delivery)

    assert source.count("persist_private_tournament_sent_message(") == 2


async def test_private_persistence_failure_does_not_mark_terminal_sent(monkeypatch) -> None:
    sent_calls: list[object] = []

    async def _persist(**_kwargs) -> None:
        raise RuntimeError("persistence failed")

    async def _sent(*_args, **_kwargs) -> int:
        sent_calls.append(object())
        return 1

    monkeypatch.setattr(
        tournaments_message_delivery_persistence, "persist_standings_message_ids", _persist
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TelegramDeliveryAttemptsRepo,
        "mark_sent",
        _sent,
    )
    monkeypatch.setattr(tournaments_message_delivery_persistence, "SessionLocal", SessionLocal)
    with pytest.raises(RuntimeError, match="persistence failed"):
        await tournaments_message_delivery_persistence.persist_private_tournament_sent_message(
            cast(Any, SimpleNamespace(idempotency_key="private")),
            UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            2,
            SimpleNamespace(message_id=502),
            NOW_UTC,
        )

    assert sent_calls == []


async def test_private_terminal_cas_loss_rolls_back_outcome(monkeypatch) -> None:
    async def _persist(**_kwargs) -> None:
        return None

    async def _sent(*_args, **_kwargs) -> int:
        return 0

    monkeypatch.setattr(
        tournaments_message_delivery_persistence, "persist_standings_message_ids", _persist
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TelegramDeliveryAttemptsRepo,
        "mark_sent",
        _sent,
    )
    monkeypatch.setattr(tournaments_message_delivery_persistence, "SessionLocal", SessionLocal)
    with pytest.raises(RuntimeError, match="terminal lease was lost"):
        await tournaments_message_delivery_persistence.persist_private_tournament_sent_message(
            cast(Any, SimpleNamespace(idempotency_key="private")),
            UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            2,
            SimpleNamespace(message_id=502),
            NOW_UTC,
        )


async def test_private_original_edit_cas_loss_rolls_back_fallback_outcome(monkeypatch) -> None:
    async def _persist(**_kwargs) -> None:
        return None

    async def _sent(*_args, **_kwargs) -> int:
        return 1

    async def _skipped(*_args, **_kwargs) -> int:
        return 0

    monkeypatch.setattr(
        tournaments_message_delivery_persistence, "persist_standings_message_ids", _persist
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TelegramDeliveryAttemptsRepo,
        "mark_sent",
        _sent,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TelegramDeliveryAttemptsRepo,
        "mark_skipped",
        _skipped,
    )
    monkeypatch.setattr(tournaments_message_delivery_persistence, "SessionLocal", SessionLocal)
    with pytest.raises(RuntimeError, match="original edit lease was lost"):
        await tournaments_message_delivery_persistence.persist_private_tournament_sent_message(
            cast(Any, SimpleNamespace(idempotency_key="fallback")),
            UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            2,
            SimpleNamespace(message_id=502),
            NOW_UTC,
            replace_existing=True,
            original_target=cast(Any, SimpleNamespace(idempotency_key="original")),
        )
