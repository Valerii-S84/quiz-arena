from __future__ import annotations

import inspect
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest

from app.workers.tasks import tournaments_message_delivery_terminal, tournaments_messaging_delivery

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
) -> tournaments_message_delivery_terminal.PrivateTournamentStandingsFence:
    return tournaments_message_delivery_terminal.PrivateTournamentStandingsFence(
        tournament_id=TOURNAMENT_ID,
        user_id=2,
        expected_message_id=expected_message_id,
        expected_status=expected_status,
        expected_round=expected_round,
    )


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
        tournaments_message_delivery_terminal.TournamentParticipantsRepo,
        "compare_and_set_standings_message_id",
        _persist,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_terminal.TelegramDeliveryAttemptsRepo,
        "mark_sent",
        _sent,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_terminal.TelegramDeliveryAttemptsRepo,
        "mark_skipped",
        _skipped,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_terminal,
        "SessionLocal",
        _SessionLocal,
    )
    await tournaments_message_delivery_terminal.persist_private_tournament_sent_message(
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
        tournaments_message_delivery_terminal.TournamentParticipantsRepo,
        "compare_and_set_standings_message_id",
        _persist,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_terminal.TelegramDeliveryAttemptsRepo,
        "mark_sent",
        _sent,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_terminal,
        "SessionLocal",
        _SessionLocal,
    )
    with pytest.raises(RuntimeError, match="persistence failed"):
        await tournaments_message_delivery_terminal.persist_private_tournament_sent_message(
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
        tournaments_message_delivery_terminal.TournamentParticipantsRepo,
        "compare_and_set_standings_message_id",
        _persist,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_terminal.TelegramDeliveryAttemptsRepo,
        "mark_sent",
        _sent,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_terminal,
        "SessionLocal",
        _SessionLocal,
    )
    with pytest.raises(RuntimeError, match="terminal lease was lost"):
        await tournaments_message_delivery_terminal.persist_private_tournament_sent_message(
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
        tournaments_message_delivery_terminal.TournamentParticipantsRepo,
        "compare_and_set_standings_message_id",
        _persist,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_terminal.TelegramDeliveryAttemptsRepo,
        "mark_sent",
        _sent,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_terminal.TelegramDeliveryAttemptsRepo,
        "mark_skipped",
        _skipped,
    )
    monkeypatch.setattr(
        tournaments_message_delivery_terminal,
        "SessionLocal",
        _SessionLocal,
    )
    with pytest.raises(RuntimeError, match="original edit lease was lost"):
        await tournaments_message_delivery_terminal.persist_private_tournament_sent_message(
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
