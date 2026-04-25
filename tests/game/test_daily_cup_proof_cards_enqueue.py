from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.workers.tasks import daily_cup_proof_cards
from tests.game.daily_arena_golden_support import (
    DummyBot,
    async_return,
    close_coroutine_and_raise,
    close_coroutine_with_name,
    session_local_with_sessions,
)


def test_daily_arena_proof_cards_enqueue_paths_and_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    enqueued: dict[str, object] = {}

    monkeypatch.setattr(
        daily_cup_proof_cards,
        "is_celery_task",
        lambda task: task is daily_cup_proof_cards.run_daily_cup_proof_cards,
    )
    monkeypatch.setattr(
        daily_cup_proof_cards.run_daily_cup_proof_cards,
        "apply_async",
        lambda **kwargs: enqueued.setdefault("apply_async", kwargs),
    )
    daily_cup_proof_cards.enqueue_daily_cup_proof_cards(
        tournament_id="arena-proof",
        user_id=7,
        delay_seconds=3,
    )
    assert enqueued["apply_async"] == {
        "kwargs": {
            "tournament_id": "arena-proof",
            "user_id": 7,
            "initial_delay_seconds": 0,
        },
        "countdown": 3,
    }

    monkeypatch.setattr(daily_cup_proof_cards, "is_celery_task", lambda task: False)
    monkeypatch.setattr(
        daily_cup_proof_cards,
        "run_async_job",
        lambda coroutine: enqueued.setdefault(
            "run_async_job", close_coroutine_with_name(coroutine)
        ),
    )
    daily_cup_proof_cards.enqueue_daily_cup_proof_cards(
        tournament_id="arena-proof-async",
        delay_seconds=4,
    )
    assert enqueued["run_async_job"] == "run_daily_cup_proof_cards_async"

    warnings: list[dict[str, object]] = []
    monkeypatch.setattr(
        daily_cup_proof_cards,
        "run_async_job",
        lambda coroutine: close_coroutine_and_raise(coroutine, RuntimeError("boom")),
    )
    monkeypatch.setattr(
        daily_cup_proof_cards.logger,
        "warning",
        lambda event, **kwargs: warnings.append({"event": event, **kwargs}),
    )
    daily_cup_proof_cards.enqueue_daily_cup_proof_cards(tournament_id="arena-proof-failed")
    assert warnings == [
        {
            "event": "daily_cup_proof_card_enqueue_failed",
            "tournament_id": "arena-proof-failed",
            "error_type": "RuntimeError",
        }
    ]

    monkeypatch.setattr(
        daily_cup_proof_cards,
        "run_async_job",
        lambda coroutine: {"wrapped": close_coroutine_with_name(coroutine)},
    )
    wrapped = daily_cup_proof_cards.run_daily_cup_proof_cards(tournament_id="arena-proof-wrapper")
    assert wrapped == {"wrapped": "run_daily_cup_proof_cards_async"}


@pytest.mark.asyncio
async def test_daily_arena_proof_cards_winner_rewards_use_blocking_tournament_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament_id = daily_cup_proof_cards.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    context = SimpleNamespace(parsed_tournament_id=tournament_id)
    captured: list[dict[str, object]] = []

    async def _fake_get_by_id_for_update(session, parsed_tournament_id, **kwargs):
        del session
        captured.append(
            {
                "parsed_tournament_id": parsed_tournament_id,
                "skip_locked": kwargs.get("skip_locked", False),
            }
        )
        return SimpleNamespace(id=parsed_tournament_id)

    monkeypatch.setattr(
        daily_cup_proof_cards,
        "SessionLocal",
        session_local_with_sessions(SimpleNamespace()),
    )
    monkeypatch.setattr(
        daily_cup_proof_cards.TournamentsRepo,
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )
    monkeypatch.setattr(
        daily_cup_proof_cards,
        "grant_daily_cup_winner_rewards",
        async_return([]),
    )

    result = await daily_cup_proof_cards._grant_winner_rewards_once(
        bot=DummyBot(),
        context=context,
        tournament_id=str(tournament_id),
        now_utc=datetime(2026, 3, 1, 18, 30, tzinfo=UTC),
    )

    assert result == []
    assert captured == [
        {
            "parsed_tournament_id": tournament_id,
            "skip_locked": False,
        }
    ]
