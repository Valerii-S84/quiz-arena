from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from app.game.tournaments import daily_cup_scoring
from tests.game.tournaments_unit_support import NOW_UTC, TournamentSession, async_return, match_row


@pytest.mark.asyncio
async def test_build_daily_cup_player_results_for_finished_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    durations: list[tuple[int, int]] = [(11, 700), (22, 900)]

    async def _duration(_session, *, user_id: int, **_kwargs) -> int:
        expected_user_id, value = durations.pop(0)
        assert user_id == expected_user_id
        return value

    challenge = SimpleNamespace(
        id=1,
        creator_user_id=11,
        opponent_user_id=22,
        creator_finished_at=NOW_UTC,
        opponent_finished_at=NOW_UTC,
        creator_answered_round=5,
        opponent_answered_round=5,
        total_rounds=5,
        creator_score=4,
        opponent_score=4,
    )
    monkeypatch.setattr(
        daily_cup_scoring.QuizSessionsRepo,
        "sum_completed_duration_ms_for_friend_challenge_user",
        _duration,
    )

    creator, opponent = await daily_cup_scoring.build_daily_cup_player_results(
        TournamentSession(),
        match=match_row(),
        challenge=challenge,
        winner_id=None,
    )

    assert creator.player_id == 11
    assert creator.wins == 1
    assert creator.is_draw
    assert creator.total_time_ms == 700
    assert opponent is not None
    assert opponent.player_id == 22
    assert opponent.wins == 1
    assert opponent.total_time_ms == 900


@pytest.mark.asyncio
async def test_build_daily_cup_player_results_for_unfinished_bye() -> None:
    challenge = SimpleNamespace(
        id=1,
        creator_user_id=11,
        opponent_user_id=None,
        creator_finished_at=None,
        opponent_finished_at=None,
        creator_answered_round=0,
        opponent_answered_round=0,
        total_rounds=5,
        creator_score=4,
        opponent_score=2,
    )

    creator, opponent = await daily_cup_scoring.build_daily_cup_player_results(
        TournamentSession(),
        match=match_row(user_b=None),
        challenge=challenge,
        winner_id=None,
    )

    assert creator.player_id == 11
    assert creator.correct_answers == 0
    assert creator.wins == 0
    assert creator.auto_finished
    assert creator.total_time_ms == 2_147_483_647
    assert opponent is None


@pytest.mark.asyncio
async def test_store_daily_cup_player_result_updates_aggregate_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    async def _upsert(_session, *, payload) -> None:
        calls.append({"payload": payload})

    async def _set_score(_session, **kwargs) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(daily_cup_scoring.TournamentRoundScoresRepo, "upsert_result", _upsert)
    monkeypatch.setattr(
        daily_cup_scoring.TournamentRoundScoresRepo,
        "aggregate_player_totals",
        async_return((3, 17)),
    )
    monkeypatch.setattr(daily_cup_scoring.TournamentParticipantsRepo, "set_score", _set_score)
    result = daily_cup_scoring.DailyCupPlayerResult(
        player_id=11,
        opponent_id=22,
        wins=2,
        correct_answers=5,
        total_time_ms=1000,
        is_draw=False,
        auto_finished=False,
        got_bye=False,
    )

    await daily_cup_scoring.store_daily_cup_player_result(
        TournamentSession(),
        match=match_row(),
        result=result,
        created_at=NOW_UTC + timedelta(minutes=1),
    )

    assert calls[0]["payload"].player_id == 11
    assert calls[1]["score"] == 3
    assert calls[1]["tie_break"] == 17
