from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.daily_runs_repo import DailyRunsRepo
from app.economy.streak.service import StreakService

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


async def build_daily_replay_state(
    session: AsyncSession,
    *,
    replay_session: QuizSession,
    current_streak: int,
    best_streak: int,
) -> DailyAnswerState:
    if replay_session.daily_run_id is None:
        return DailyAnswerState(
            daily_run_id=None,
            current_question=0,
            total_questions=DAILY_CHALLENGE_TOTAL_QUESTIONS,
            score=0,
            completed=False,
            current_streak=current_streak,
            best_streak=best_streak,
        )

    run = await DailyRunsRepo.get_by_id(session, replay_session.daily_run_id)
    if run is None:
        return DailyAnswerState(
            daily_run_id=replay_session.daily_run_id,
            current_question=0,
            total_questions=DAILY_CHALLENGE_TOTAL_QUESTIONS,
            score=0,
            completed=False,
            current_streak=current_streak,
            best_streak=best_streak,
        )

    return DailyAnswerState(
        daily_run_id=run.id,
        current_question=run.current_question,
        total_questions=DAILY_CHALLENGE_TOTAL_QUESTIONS,
        score=run.score,
        completed=run.status == "COMPLETED",
        current_streak=current_streak,
        best_streak=best_streak,
    )


async def apply_daily_answer(
    session: AsyncSession,
    *,
    user_id: int,
    quiz_session: QuizSession,
    is_correct: bool,
    now_utc: datetime,
) -> DailyAnswerState:
    if quiz_session.daily_run_id is None:
        streak_snapshot = await StreakService.sync_rollover(
            session,
            user_id=user_id,
            now_utc=now_utc,
        )
        return DailyAnswerState(
            daily_run_id=None,
            current_question=1,
            total_questions=DAILY_CHALLENGE_TOTAL_QUESTIONS,
            score=1 if is_correct else 0,
            completed=False,
            current_streak=streak_snapshot.current_streak,
            best_streak=streak_snapshot.best_streak,
        )

    run = await DailyRunsRepo.get_by_id_for_update(session, quiz_session.daily_run_id)
    if run is None:
        streak_snapshot = await StreakService.sync_rollover(
            session,
            user_id=user_id,
            now_utc=now_utc,
        )
        return DailyAnswerState(
            daily_run_id=quiz_session.daily_run_id,
            current_question=1,
            total_questions=DAILY_CHALLENGE_TOTAL_QUESTIONS,
            score=1 if is_correct else 0,
            completed=False,
            current_streak=streak_snapshot.current_streak,
            best_streak=streak_snapshot.best_streak,
        )

    completed_now = False
    if run.status != "COMPLETED":
        run.status = "IN_PROGRESS"
        run.completed_at = None
        run.current_question = min(DAILY_CHALLENGE_TOTAL_QUESTIONS, run.current_question + 1)
        if is_correct:
            run.score = min(DAILY_CHALLENGE_TOTAL_QUESTIONS, run.score + 1)
        if run.current_question >= DAILY_CHALLENGE_TOTAL_QUESTIONS:
            run.status = "COMPLETED"
            run.completed_at = now_utc
            completed_now = True

    if completed_now:
        streak_activity = await StreakService.record_activity(
            session,
            user_id=user_id,
            activity_at_utc=now_utc,
        )
        current_streak = streak_activity.current_streak
        best_streak = streak_activity.best_streak
        await emit_analytics_event(
            session,
            event_type="daily_completed",
            source=EVENT_SOURCE_BOT,
            happened_at=now_utc,
            user_id=user_id,
            payload={
                "daily_run_id": str(run.id),
                "berlin_date": run.berlin_date.isoformat(),
                "score": run.score,
                "total_questions": DAILY_CHALLENGE_TOTAL_QUESTIONS,
            },
        )
    else:
        streak_snapshot = await StreakService.sync_rollover(
            session,
            user_id=user_id,
            now_utc=now_utc,
        )
        current_streak = streak_snapshot.current_streak
        best_streak = streak_snapshot.best_streak

    return DailyAnswerState(
        daily_run_id=run.id,
        current_question=run.current_question,
        total_questions=DAILY_CHALLENGE_TOTAL_QUESTIONS,
        score=run.score,
        completed=run.status == "COMPLETED",
        current_streak=current_streak,
        best_streak=best_streak,
    )
