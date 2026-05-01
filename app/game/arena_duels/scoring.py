from __future__ import annotations

from dataclasses import dataclass

from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_RESULT_DRAW,
    ARENA_ATTEMPT_RESULT_LOSS,
    ARENA_ATTEMPT_RESULT_WIN,
    ARENA_RESULT_REASON_EXACT_TIE,
    ARENA_RESULT_REASON_SCORE,
    ARENA_RESULT_REASON_TIME,
)
from app.game.duels.constants import DUEL_QUESTION_COUNT


@dataclass(frozen=True, slots=True)
class ArenaScoreLine:
    user_id: int
    score: int
    time_ms: int


@dataclass(frozen=True, slots=True)
class ArenaScoringOutcome:
    winner_user_id: int | None
    challenger_result: str
    baseline_result: str
    reason: str

    @property
    def challenger_won(self) -> bool:
        return self.challenger_result == ARENA_ATTEMPT_RESULT_WIN


def decide_arena_scoring_outcome(
    *,
    baseline: ArenaScoreLine,
    challenger: ArenaScoreLine,
) -> ArenaScoringOutcome:
    _validate_score_line(baseline)
    _validate_score_line(challenger)

    if challenger.score > baseline.score:
        return _challenger_wins(challenger.user_id, reason=ARENA_RESULT_REASON_SCORE)
    if challenger.score < baseline.score:
        return _baseline_wins(baseline.user_id, reason=ARENA_RESULT_REASON_SCORE)
    if challenger.time_ms < baseline.time_ms:
        return _challenger_wins(challenger.user_id, reason=ARENA_RESULT_REASON_TIME)
    if challenger.time_ms > baseline.time_ms:
        return _baseline_wins(baseline.user_id, reason=ARENA_RESULT_REASON_TIME)
    return ArenaScoringOutcome(
        winner_user_id=None,
        challenger_result=ARENA_ATTEMPT_RESULT_DRAW,
        baseline_result=ARENA_ATTEMPT_RESULT_DRAW,
        reason=ARENA_RESULT_REASON_EXACT_TIE,
    )


def _challenger_wins(winner_user_id: int, *, reason: str) -> ArenaScoringOutcome:
    return ArenaScoringOutcome(
        winner_user_id=winner_user_id,
        challenger_result=ARENA_ATTEMPT_RESULT_WIN,
        baseline_result=ARENA_ATTEMPT_RESULT_LOSS,
        reason=reason,
    )


def _baseline_wins(winner_user_id: int, *, reason: str) -> ArenaScoringOutcome:
    return ArenaScoringOutcome(
        winner_user_id=winner_user_id,
        challenger_result=ARENA_ATTEMPT_RESULT_LOSS,
        baseline_result=ARENA_ATTEMPT_RESULT_WIN,
        reason=reason,
    )


def _validate_score_line(score_line: ArenaScoreLine) -> None:
    if score_line.user_id <= 0:
        raise ValueError("arena user_id must be positive")
    if score_line.score < 0 or score_line.score > DUEL_QUESTION_COUNT:
        raise ValueError("arena score is outside the duel question range")
    if score_line.time_ms < 0:
        raise ValueError("arena time_ms must be non-negative")
