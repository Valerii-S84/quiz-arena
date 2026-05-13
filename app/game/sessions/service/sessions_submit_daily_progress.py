from __future__ import annotations

from datetime import datetime

from .constants import DAILY_CHALLENGE_TOTAL_QUESTIONS


def advance_daily_run(run, *, is_correct: bool, now_utc: datetime) -> bool:
    if run.status == "COMPLETED":
        return False

    run.status = "IN_PROGRESS"
    run.completed_at = None
    run.current_question = min(DAILY_CHALLENGE_TOTAL_QUESTIONS, run.current_question + 1)
    if is_correct:
        run.score = min(DAILY_CHALLENGE_TOTAL_QUESTIONS, run.score + 1)
    if run.current_question < DAILY_CHALLENGE_TOTAL_QUESTIONS:
        return False

    run.status = "COMPLETED"
    run.completed_at = now_utc
    return True
