from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.game.tournaments.constants import (
    TOURNAMENT_STATUS_COMPLETED,
    TOURNAMENT_STATUS_REGISTRATION,
)
from app.workers.tasks import daily_cup_proof_cards
from tests.game.daily_arena_golden_support import (
    DummyBot,
    async_return,
    close_coroutine_and_raise,
    close_coroutine_with_name,
    make_standing_row,
    make_worker_user,
    session_local_with_sessions,
    status_tournament,
)


def _arena_tournament(*, status: str, current_round: int = 0) -> SimpleNamespace:
    tournament = status_tournament(status=status, current_round=current_round)
    tournament.round_deadline = datetime(2026, 3, 1, 18, 30, tzinfo=UTC)
    return tournament


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tournament", "standings", "expected"),
    [
        (None, [make_standing_row(user_id=101, place=1)], daily_cup_proof_cards._empty_result()),
        (
            _arena_tournament(status=TOURNAMENT_STATUS_REGISTRATION),
            [make_standing_row(user_id=101, place=1)],
            daily_cup_proof_cards._empty_result(),
        ),
        (
            _arena_tournament(status=TOURNAMENT_STATUS_COMPLETED),
            [],
            daily_cup_proof_cards._empty_result(),
        ),
    ],
    ids=["missing_tournament", "not_completed", "empty_standings"],
)
async def test_daily_arena_proof_cards_short_circuit_for_invalid_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tournament: SimpleNamespace | None,
    standings: list[SimpleNamespace],
    expected: dict[str, int],
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    monkeypatch.setattr(
        daily_cup_proof_cards,
        "SessionLocal",
        session_local_with_sessions(SimpleNamespace()),
    )
    monkeypatch.setattr(daily_cup_proof_cards.TournamentsRepo, "get_by_id", async_return(tournament))
    monkeypatch.setattr(daily_cup_proof_cards, "is_today_daily_cup_tournament", lambda **kwargs: True)
    monkeypatch.setattr(daily_cup_proof_cards, "calculate_daily_cup_standings", async_return(standings))

    result = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        initial_delay_seconds=0,
    )

    assert result == expected
    assert await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id="not-a-uuid",
        initial_delay_seconds=0,
    ) == daily_cup_proof_cards._empty_result()


@pytest.mark.asyncio
async def test_daily_arena_proof_cards_skip_stale_tournament_and_empty_selected_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    tournament = _arena_tournament(status=TOURNAMENT_STATUS_COMPLETED, current_round=3)
    stale_logs: list[dict[str, object]] = []
    monkeypatch.setattr(
        daily_cup_proof_cards,
        "SessionLocal",
        session_local_with_sessions(SimpleNamespace(), SimpleNamespace()),
    )
    monkeypatch.setattr(daily_cup_proof_cards.TournamentsRepo, "get_by_id", async_return(tournament))
    monkeypatch.setattr(
        daily_cup_proof_cards.logger,
        "info",
        lambda event, **kwargs: stale_logs.append({"event": event, **kwargs}),
    )
    monkeypatch.setattr(daily_cup_proof_cards, "is_today_daily_cup_tournament", lambda **kwargs: False)

    stale = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=str(tournament.id),
        initial_delay_seconds=0,
    )

    monkeypatch.setattr(daily_cup_proof_cards, "is_today_daily_cup_tournament", lambda **kwargs: True)
    monkeypatch.setattr(
        daily_cup_proof_cards,
        "calculate_daily_cup_standings",
        async_return([make_standing_row(user_id=101, place=1)]),
    )
    monkeypatch.setattr(
        daily_cup_proof_cards.UsersRepo,
        "list_by_ids",
        async_return([make_worker_user(user_id=101)]),
    )
    monkeypatch.setattr(
        daily_cup_proof_cards.TournamentMatchesRepo,
        "get_max_round_no",
        async_return(3),
    )
    empty_selected = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=str(tournament.id),
        user_id=999,
        initial_delay_seconds=0,
    )

    assert stale == daily_cup_proof_cards._empty_result()
    assert stale_logs[0]["event"] == "daily_cup_proof_cards_skipped_stale_tournament"
    assert empty_selected == {
        "processed": 1,
        "participants_total": 0,
        "sent": 0,
        "cached_reused": 0,
        "failed": 0,
    }


@pytest.mark.asyncio
async def test_daily_arena_proof_cards_pipeline_handles_delivery_edge_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    tournament = _arena_tournament(status=TOURNAMENT_STATUS_COMPLETED, current_round=3)
    standings = [
        make_standing_row(user_id=101, place=1, score="7"),
        make_standing_row(user_id=202, place=2, score="6"),
        make_standing_row(user_id=303, place=3, score="5", proof_card_sent=True),
        make_standing_row(user_id=404, place=4, score="4"),
        make_standing_row(user_id=505, place=5, score="3"),
    ]
    sleep_calls: list[int] = []
    send_calls: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    persisted_sent: list[int] = []
    persisted_files: list[tuple[int, str]] = []
    bot = DummyBot()

    async def _fake_send_proof_card(**kwargs):
        send_calls.append(kwargs)
        if kwargs["user_id"] == 101:
            return True, False, "arena-proof-file"
        if kwargs["user_id"] == 404:
            return False, False, None
        raise FileNotFoundError("image missing")

    async def _fake_sleep(seconds: int) -> None:
        sleep_calls.append(seconds)

    async def _fake_mark_sent(session, *, tournament_id, user_id) -> None:
        del session, tournament_id
        persisted_sent.append(user_id)

    async def _fake_store_file_id(session, *, tournament_id, user_id, file_id) -> None:
        del session, tournament_id
        persisted_files.append((user_id, file_id))

    monkeypatch.setattr(
        daily_cup_proof_cards,
        "SessionLocal",
        session_local_with_sessions(SimpleNamespace(), SimpleNamespace()),
    )
    monkeypatch.setattr(daily_cup_proof_cards.TournamentsRepo, "get_by_id", async_return(tournament))
    monkeypatch.setattr(daily_cup_proof_cards, "is_today_daily_cup_tournament", lambda **kwargs: True)
    monkeypatch.setattr(daily_cup_proof_cards, "calculate_daily_cup_standings", async_return(standings))
    monkeypatch.setattr(
        daily_cup_proof_cards.UsersRepo,
        "list_by_ids",
        async_return(
            [
                make_worker_user(user_id=101),
                make_worker_user(user_id=303),
                make_worker_user(user_id=404),
                make_worker_user(user_id=505),
            ]
        ),
    )
    monkeypatch.setattr(daily_cup_proof_cards.TournamentMatchesRepo, "get_max_round_no", async_return(3))
    monkeypatch.setattr(daily_cup_proof_cards, "build_bot", lambda: bot)
    monkeypatch.setattr(daily_cup_proof_cards, "send_daily_cup_proof_card", _fake_send_proof_card)
    monkeypatch.setattr(daily_cup_proof_cards.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(
        daily_cup_proof_cards.TournamentParticipantsRepo,
        "set_proof_card_sent",
        _fake_mark_sent,
    )
    monkeypatch.setattr(
        daily_cup_proof_cards.TournamentParticipantsRepo,
        "set_proof_card_file_id_if_missing",
        _fake_store_file_id,
    )
    monkeypatch.setattr(
        daily_cup_proof_cards.logger,
        "warning",
        lambda event, **kwargs: warnings.append({"event": event, **kwargs}),
    )

    result = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=str(tournament.id),
        initial_delay_seconds=2,
    )

    assert result == {"processed": 1, "participants_total": 5, "sent": 1, "cached_reused": 0, "failed": 2}
    assert sleep_calls == [2]
    assert [call["user_id"] for call in send_calls] == [101, 404, 505]
    assert send_calls[0]["place"] == 1
    assert persisted_sent == [101]
    assert persisted_files == [(101, "arena-proof-file")]
    assert warnings == [
        {
            "event": "daily_cup_proof_card_send_failed",
            "tournament_id": str(tournament.id),
            "user_id": 505,
            "error_type": "FileNotFoundError",
        }
    ]
    assert bot.session.closed is True


@pytest.mark.asyncio
async def test_proof_card_skips_user_with_none_telegram_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament = _arena_tournament(status=TOURNAMENT_STATUS_COMPLETED, current_round=3)
    bot = DummyBot()

    async def _unexpected_send_proof_card(**kwargs):
        del kwargs
        raise AssertionError("send_daily_cup_proof_card should not be called")

    monkeypatch.setattr(
        daily_cup_proof_cards,
        "SessionLocal",
        session_local_with_sessions(SimpleNamespace()),
    )
    monkeypatch.setattr(daily_cup_proof_cards.TournamentsRepo, "get_by_id", async_return(tournament))
    monkeypatch.setattr(daily_cup_proof_cards, "is_today_daily_cup_tournament", lambda **kwargs: True)
    monkeypatch.setattr(
        daily_cup_proof_cards,
        "calculate_daily_cup_standings",
        async_return([make_standing_row(user_id=101, place=1, score="7")]),
    )
    monkeypatch.setattr(
        daily_cup_proof_cards.UsersRepo,
        "list_by_ids",
        async_return([make_worker_user(user_id=101, telegram_user_id=None)]),
    )
    monkeypatch.setattr(daily_cup_proof_cards.TournamentMatchesRepo, "get_max_round_no", async_return(3))
    monkeypatch.setattr(daily_cup_proof_cards, "build_bot", lambda: bot)
    monkeypatch.setattr(
        daily_cup_proof_cards,
        "send_daily_cup_proof_card",
        _unexpected_send_proof_card,
    )

    result = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=str(tournament.id),
        initial_delay_seconds=0,
    )

    assert result == {
        "processed": 1,
        "participants_total": 1,
        "sent": 0,
        "cached_reused": 0,
        "failed": 1,
    }
    assert bot.session.closed is True


def test_daily_arena_proof_cards_enqueue_paths_and_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    enqueued: dict[str, object] = {}

    monkeypatch.setattr(daily_cup_proof_cards, "is_celery_task", lambda task: task is daily_cup_proof_cards.run_daily_cup_proof_cards)
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
        lambda coroutine: enqueued.setdefault("run_async_job", close_coroutine_with_name(coroutine)),
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
