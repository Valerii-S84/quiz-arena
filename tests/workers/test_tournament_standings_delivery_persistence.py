from __future__ import annotations

import inspect
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import SendMessage

from app.workers.tasks import (
    tournaments_message_delivery_persistence,
    tournaments_messaging_delivery,
)

NOW_UTC = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
TOURNAMENT_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


class _SessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_args: object) -> None:
        return None


class _SessionLocal:
    @staticmethod
    def begin() -> _SessionContext:
        return _SessionContext()


def _fence(
    *,
    expected_message_id: int | None,
    expected_status: str,
    expected_round: int,
) -> tournaments_message_delivery_persistence.PrivateTournamentStandingsFence:
    return tournaments_message_delivery_persistence.PrivateTournamentStandingsFence(
        tournament_id=TOURNAMENT_ID,
        user_id=2,
        expected_message_id=expected_message_id,
        expected_status=expected_status,
        expected_round=expected_round,
    )


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
        return SimpleNamespace(status="PENDING"), False

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


async def test_private_retryable_failure_marks_failed_without_defer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_calls: list[Any] = []
    deferred_calls: list[object] = []

    async def _mark_failed(_session: object, **kwargs: object) -> bool:
        failed_calls.append(kwargs["failure"])
        return True

    async def _defer_retry_after(_session: object, **kwargs: object) -> bool:
        deferred_calls.append(kwargs)
        return True

    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TelegramDeliveryAttemptsRepo,
        "mark_failed",
        _mark_failed,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TelegramDeliveryAttemptsRepo,
        "defer_retry_after",
        _defer_retry_after,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence,
        "SessionLocal",
        _SessionLocal,
    )

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
    assert len(failed_calls) == 1
    assert failed_calls[0].failure_code == "TELEGRAM_RETRY_NEEDED"
    assert deferred_calls == []


@pytest.mark.parametrize("fallback", [False, True])
async def test_private_message_id_persists_before_terminal_sent(
    monkeypatch: pytest.MonkeyPatch,
    fallback: bool,
) -> None:
    calls: list[str] = []
    persisted: dict[str, object] = {}

    async def _persist(_session: object, **kwargs: object) -> int:
        persisted.update(kwargs)
        calls.append("persist")
        return 1

    async def _sent(*_args: object, **_kwargs: object) -> int:
        calls.append("sent")
        return 1

    async def _skipped(*_args: object, **_kwargs: object) -> int:
        calls.append("skipped")
        return 1

    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TournamentParticipantsRepo,
        "compare_and_set_standings_message_id",
        _persist,
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
    monkeypatch.setattr(
        tournaments_message_delivery_persistence,
        "SessionLocal",
        _SessionLocal,
    )
    await tournaments_message_delivery_persistence.persist_private_tournament_sent_message(
        cast(Any, SimpleNamespace(idempotency_key="private")),
        _fence(
            expected_message_id=222 if fallback else None,
            expected_status="ROUND_2",
            expected_round=2,
        ),
        SimpleNamespace(message_id=502),
        NOW_UTC,
        original_target=(
            cast(Any, SimpleNamespace(idempotency_key="original")) if fallback else None
        ),
    )

    assert persisted["expected_message_id"] == (222 if fallback else None)
    assert persisted["message_id"] == 502
    assert persisted["expected_status"] == "ROUND_2"
    assert persisted["expected_round"] == 2
    assert calls == (["persist", "sent", "skipped"] if fallback else ["persist", "sent"])


def test_private_delivery_uses_persistence_helper_for_send_edit_and_fallback() -> None:
    source = inspect.getsource(tournaments_messaging_delivery)

    assert source.count("persist_private_tournament_sent_message(") == 3


async def test_private_persistence_failure_does_not_mark_terminal_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_calls: list[object] = []

    async def _persist(*_args: object, **_kwargs: object) -> int:
        raise RuntimeError("persistence failed")

    async def _sent(*_args: object, **_kwargs: object) -> int:
        sent_calls.append(object())
        return 1

    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TournamentParticipantsRepo,
        "compare_and_set_standings_message_id",
        _persist,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TelegramDeliveryAttemptsRepo,
        "mark_sent",
        _sent,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence,
        "SessionLocal",
        _SessionLocal,
    )
    with pytest.raises(RuntimeError, match="persistence failed"):
        await tournaments_message_delivery_persistence.persist_private_tournament_sent_message(
            cast(Any, SimpleNamespace(idempotency_key="private")),
            _fence(
                expected_message_id=None,
                expected_status="ROUND_1",
                expected_round=1,
            ),
            SimpleNamespace(message_id=502),
            NOW_UTC,
        )

    assert sent_calls == []


async def test_private_terminal_cas_loss_rolls_back_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _persist(*_args: object, **_kwargs: object) -> int:
        return 1

    async def _sent(*_args: object, **_kwargs: object) -> int:
        return 0

    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TournamentParticipantsRepo,
        "compare_and_set_standings_message_id",
        _persist,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TelegramDeliveryAttemptsRepo,
        "mark_sent",
        _sent,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_persistence,
        "SessionLocal",
        _SessionLocal,
    )
    with pytest.raises(RuntimeError, match="terminal lease was lost"):
        await tournaments_message_delivery_persistence.persist_private_tournament_sent_message(
            cast(Any, SimpleNamespace(idempotency_key="private")),
            _fence(
                expected_message_id=None,
                expected_status="ROUND_1",
                expected_round=1,
            ),
            SimpleNamespace(message_id=502),
            NOW_UTC,
        )


async def test_private_original_edit_cas_loss_rolls_back_fallback_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _persist(*_args: object, **_kwargs: object) -> int:
        return 1

    async def _sent(*_args: object, **_kwargs: object) -> int:
        return 1

    async def _skipped(*_args: object, **_kwargs: object) -> int:
        return 0

    monkeypatch.setattr(
        tournaments_message_delivery_persistence.TournamentParticipantsRepo,
        "compare_and_set_standings_message_id",
        _persist,
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
    monkeypatch.setattr(
        tournaments_message_delivery_persistence,
        "SessionLocal",
        _SessionLocal,
    )
    with pytest.raises(RuntimeError, match="original edit lease was lost"):
        await tournaments_message_delivery_persistence.persist_private_tournament_sent_message(
            cast(Any, SimpleNamespace(idempotency_key="fallback")),
            _fence(
                expected_message_id=222,
                expected_status="ROUND_2",
                expected_round=2,
            ),
            SimpleNamespace(message_id=502),
            NOW_UTC,
            original_target=cast(Any, SimpleNamespace(idempotency_key="original")),
        )
