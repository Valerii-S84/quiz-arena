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
    assert daily_cup_proof_cards.enqueue_daily_cup_proof_cards(
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
    assert daily_cup_proof_cards.enqueue_daily_cup_proof_cards(
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
    assert (
        daily_cup_proof_cards.enqueue_daily_cup_proof_cards(tournament_id="arena-proof-failed")
        is False
    )
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


@pytest.mark.asyncio
async def test_daily_arena_proof_cards_queue_retry_when_participant_row_lock_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament_id = daily_cup_proof_cards.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    queued: list[dict[str, object]] = []
    infos: list[dict[str, object]] = []
    bot = DummyBot()
    context = SimpleNamespace(
        parsed_tournament_id=tournament_id,
        participants=[SimpleNamespace(user_id=101)],
        participants_total=1,
        telegram_targets={101: 900101},
        standings_user_ids=[101],
        points_by_user={101: "7"},
        user_labels={101: "Spieler"},
        rounds_played=3,
    )

    def _fake_enqueue_retry(**kwargs: object) -> bool:
        queued.append(dict(kwargs))
        return True

    monkeypatch.setattr(
        daily_cup_proof_cards,
        "_load_proof_cards_context",
        async_return(context),
    )
    monkeypatch.setattr(daily_cup_proof_cards, "build_bot", lambda: bot)
    monkeypatch.setattr(
        daily_cup_proof_cards,
        "enqueue_daily_cup_proof_cards",
        _fake_enqueue_retry,
    )
    monkeypatch.setattr(
        daily_cup_proof_cards.TournamentParticipantsRepo,
        "get_for_tournament_user_for_update",
        async_return(None),
    )
    monkeypatch.setattr(
        daily_cup_proof_cards,
        "send_daily_cup_proof_card",
        async_return((True, False, "should-not-send")),
    )
    monkeypatch.setattr(
        daily_cup_proof_cards,
        "SessionLocal",
        session_local_with_sessions(SimpleNamespace()),
    )
    monkeypatch.setattr(
        daily_cup_proof_cards.logger,
        "info",
        lambda event, **kwargs: infos.append({"event": event, **kwargs}),
    )

    result = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=str(tournament_id),
        initial_delay_seconds=0,
    )

    assert result == {
        "processed": 1,
        "participants_total": 1,
        "sent": 0,
        "cached_reused": 0,
        "failed": 0,
    }
    assert queued == [
        {
            "tournament_id": str(tournament_id),
            "user_id": 101,
            "delay_seconds": 2,
        }
    ]
    assert infos == [
        {
            "event": "daily_cup_proof_card_retry_queued",
            "tournament_id": str(tournament_id),
            "user_id": 101,
            "reason": "participant_row_lock_skipped",
        }
    ]
    assert bot.session.closed is True


@pytest.mark.asyncio
async def test_daily_arena_proof_cards_do_not_log_retry_queued_when_enqueue_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament_id = daily_cup_proof_cards.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    infos: list[dict[str, object]] = []
    bot = DummyBot()
    context = SimpleNamespace(
        parsed_tournament_id=tournament_id,
        participants=[SimpleNamespace(user_id=101)],
        participants_total=1,
        telegram_targets={101: 900101},
        standings_user_ids=[101],
        points_by_user={101: "7"},
        user_labels={101: "Spieler"},
        rounds_played=3,
    )

    monkeypatch.setattr(
        daily_cup_proof_cards,
        "_load_proof_cards_context",
        async_return(context),
    )
    monkeypatch.setattr(daily_cup_proof_cards, "build_bot", lambda: bot)
    monkeypatch.setattr(
        daily_cup_proof_cards,
        "enqueue_daily_cup_proof_cards",
        lambda **kwargs: False,
    )
    monkeypatch.setattr(
        daily_cup_proof_cards.TournamentParticipantsRepo,
        "get_for_tournament_user_for_update",
        async_return(None),
    )
    monkeypatch.setattr(
        daily_cup_proof_cards,
        "SessionLocal",
        session_local_with_sessions(SimpleNamespace()),
    )
    monkeypatch.setattr(
        daily_cup_proof_cards.logger,
        "info",
        lambda event, **kwargs: infos.append({"event": event, **kwargs}),
    )

    result = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=str(tournament_id),
        initial_delay_seconds=0,
    )

    assert result == {
        "processed": 1,
        "participants_total": 1,
        "sent": 0,
        "cached_reused": 0,
        "failed": 0,
    }
    assert infos == []
    assert bot.session.closed is True
