from __future__ import annotations

import inspect

import pytest

from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_RESULT_DRAW,
    ARENA_ATTEMPT_RESULT_LOSS,
    ARENA_ATTEMPT_RESULT_WIN,
    ARENA_RESULT_REASON_EXACT_TIE,
    ARENA_RESULT_REASON_SCORE,
    ARENA_RESULT_REASON_TIME,
)
from app.game.arena_duels.scoring import ArenaScoreLine, decide_arena_scoring_outcome


def test_challenger_wins_by_higher_score_even_when_slower() -> None:
    outcome = decide_arena_scoring_outcome(
        baseline=ArenaScoreLine(user_id=11, score=6, time_ms=48_000),
        challenger=ArenaScoreLine(user_id=22, score=7, time_ms=52_000),
    )

    assert outcome.winner_user_id == 22
    assert outcome.challenger_result == ARENA_ATTEMPT_RESULT_WIN
    assert outcome.baseline_result == ARENA_ATTEMPT_RESULT_LOSS
    assert outcome.reason == ARENA_RESULT_REASON_SCORE
    assert outcome.challenger_won is True


def test_challenger_loses_by_lower_score_even_when_faster() -> None:
    outcome = decide_arena_scoring_outcome(
        baseline=ArenaScoreLine(user_id=11, score=6, time_ms=48_000),
        challenger=ArenaScoreLine(user_id=22, score=5, time_ms=31_000),
    )

    assert outcome.winner_user_id == 11
    assert outcome.challenger_result == ARENA_ATTEMPT_RESULT_LOSS
    assert outcome.baseline_result == ARENA_ATTEMPT_RESULT_WIN
    assert outcome.reason == ARENA_RESULT_REASON_SCORE
    assert outcome.challenger_won is False


def test_challenger_wins_equal_score_by_faster_time() -> None:
    outcome = decide_arena_scoring_outcome(
        baseline=ArenaScoreLine(user_id=11, score=6, time_ms=48_000),
        challenger=ArenaScoreLine(user_id=22, score=6, time_ms=42_000),
    )

    assert outcome.winner_user_id == 22
    assert outcome.challenger_result == ARENA_ATTEMPT_RESULT_WIN
    assert outcome.baseline_result == ARENA_ATTEMPT_RESULT_LOSS
    assert outcome.reason == ARENA_RESULT_REASON_TIME


def test_challenger_loses_equal_score_by_slower_time() -> None:
    outcome = decide_arena_scoring_outcome(
        baseline=ArenaScoreLine(user_id=11, score=6, time_ms=48_000),
        challenger=ArenaScoreLine(user_id=22, score=6, time_ms=55_000),
    )

    assert outcome.winner_user_id == 11
    assert outcome.challenger_result == ARENA_ATTEMPT_RESULT_LOSS
    assert outcome.baseline_result == ARENA_ATTEMPT_RESULT_WIN
    assert outcome.reason == ARENA_RESULT_REASON_TIME


def test_exact_score_and_time_tie_has_no_winner() -> None:
    outcome = decide_arena_scoring_outcome(
        baseline=ArenaScoreLine(user_id=11, score=6, time_ms=48_000),
        challenger=ArenaScoreLine(user_id=22, score=6, time_ms=48_000),
    )

    assert outcome.winner_user_id is None
    assert outcome.challenger_result == ARENA_ATTEMPT_RESULT_DRAW
    assert outcome.baseline_result == ARENA_ATTEMPT_RESULT_DRAW
    assert outcome.reason == ARENA_RESULT_REASON_EXACT_TIE
    assert outcome.challenger_won is False


def test_perfect_scores_use_time_tie_break_for_baseline() -> None:
    outcome = decide_arena_scoring_outcome(
        baseline=ArenaScoreLine(user_id=11, score=7, time_ms=39_000),
        challenger=ArenaScoreLine(user_id=22, score=7, time_ms=40_000),
    )

    assert outcome.winner_user_id == 11
    assert outcome.challenger_result == ARENA_ATTEMPT_RESULT_LOSS
    assert outcome.baseline_result == ARENA_ATTEMPT_RESULT_WIN
    assert outcome.reason == ARENA_RESULT_REASON_TIME


def test_zero_scores_still_use_time_tie_break() -> None:
    outcome = decide_arena_scoring_outcome(
        baseline=ArenaScoreLine(user_id=11, score=0, time_ms=30_000),
        challenger=ArenaScoreLine(user_id=22, score=0, time_ms=25_000),
    )

    assert outcome.winner_user_id == 22
    assert outcome.challenger_result == ARENA_ATTEMPT_RESULT_WIN
    assert outcome.baseline_result == ARENA_ATTEMPT_RESULT_LOSS
    assert outcome.reason == ARENA_RESULT_REASON_TIME


def test_score_priority_ignores_extreme_challenger_speed() -> None:
    outcome = decide_arena_scoring_outcome(
        baseline=ArenaScoreLine(user_id=11, score=7, time_ms=90_000),
        challenger=ArenaScoreLine(user_id=22, score=6, time_ms=1),
    )

    assert outcome.winner_user_id == 11
    assert outcome.challenger_result == ARENA_ATTEMPT_RESULT_LOSS
    assert outcome.reason == ARENA_RESULT_REASON_SCORE


def test_score_priority_ignores_extreme_baseline_speed() -> None:
    outcome = decide_arena_scoring_outcome(
        baseline=ArenaScoreLine(user_id=11, score=6, time_ms=1),
        challenger=ArenaScoreLine(user_id=22, score=7, time_ms=90_000),
    )

    assert outcome.winner_user_id == 22
    assert outcome.challenger_result == ARENA_ATTEMPT_RESULT_WIN
    assert outcome.reason == ARENA_RESULT_REASON_SCORE


def test_scoring_contract_has_no_premium_or_access_input() -> None:
    params = set(inspect.signature(decide_arena_scoring_outcome).parameters)

    assert params == {"baseline", "challenger"}


def test_invalid_baseline_score_line_is_rejected() -> None:
    with pytest.raises(ValueError):
        decide_arena_scoring_outcome(
            baseline=ArenaScoreLine(user_id=11, score=8, time_ms=48_000),
            challenger=ArenaScoreLine(user_id=22, score=6, time_ms=48_000),
        )


@pytest.mark.parametrize(
    "score_line",
    [
        ArenaScoreLine(user_id=0, score=6, time_ms=48_000),
        ArenaScoreLine(user_id=11, score=-1, time_ms=48_000),
        ArenaScoreLine(user_id=11, score=8, time_ms=48_000),
        ArenaScoreLine(user_id=11, score=6, time_ms=-1),
    ],
)
def test_invalid_score_lines_are_rejected(score_line: ArenaScoreLine) -> None:
    with pytest.raises(ValueError):
        decide_arena_scoring_outcome(
            baseline=ArenaScoreLine(user_id=11, score=6, time_ms=48_000),
            challenger=score_line,
        )
