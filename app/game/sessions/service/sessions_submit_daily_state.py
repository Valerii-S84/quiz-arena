from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from .constants import DAILY_CHALLENGE_TOTAL_QUESTIONS


@dataclass(frozen=True, slots=True)
class DailyAnswerState:
    daily_run_id: UUID | None
    current_question: int
    total_questions: int
    score: int
    completed: bool
    current_streak: int
    best_streak: int


def build_missing_daily_run_state(
    *,
    daily_run_id: UUID | None,
    is_correct: bool,
    current_streak: int,
    best_streak: int,
) -> DailyAnswerState:
    return DailyAnswerState(
        daily_run_id=daily_run_id,
        current_question=1,
        total_questions=DAILY_CHALLENGE_TOTAL_QUESTIONS,
        score=1 if is_correct else 0,
        completed=False,
        current_streak=current_streak,
        best_streak=best_streak,
    )


def build_daily_run_snapshot_state(
    *,
    daily_run_id: UUID | None,
    current_question: int,
    score: int,
    completed: bool,
    current_streak: int,
    best_streak: int,
) -> DailyAnswerState:
    return DailyAnswerState(
        daily_run_id=daily_run_id,
        current_question=current_question,
        total_questions=DAILY_CHALLENGE_TOTAL_QUESTIONS,
        score=score,
        completed=completed,
        current_streak=current_streak,
        best_streak=best_streak,
    )


def build_existing_daily_run_state(
    *,
    run,
    current_streak: int,
    best_streak: int,
) -> DailyAnswerState:
    return build_daily_run_snapshot_state(
        daily_run_id=run.id,
        current_question=run.current_question,
        score=run.score,
        completed=run.status == "COMPLETED",
        current_streak=current_streak,
        best_streak=best_streak,
    )
