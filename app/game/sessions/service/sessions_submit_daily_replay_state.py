from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_sessions import QuizSession

from .sessions_submit_daily_state import (
    DailyAnswerState,
    build_daily_run_snapshot_state,
    build_existing_daily_run_state,
)


async def build_daily_replay_state_impl(
    session: AsyncSession,
    *,
    replay_session: QuizSession,
    current_streak: int,
    best_streak: int,
    daily_runs_repo,
) -> DailyAnswerState:
    if replay_session.daily_run_id is None:
        return build_daily_run_snapshot_state(
            daily_run_id=None,
            current_question=0,
            score=0,
            completed=False,
            current_streak=current_streak,
            best_streak=best_streak,
        )

    run = await daily_runs_repo.get_by_id(session, replay_session.daily_run_id)
    if run is None:
        return build_daily_run_snapshot_state(
            daily_run_id=replay_session.daily_run_id,
            current_question=0,
            score=0,
            completed=False,
            current_streak=current_streak,
            best_streak=best_streak,
        )

    return build_existing_daily_run_state(
        run=run,
        current_streak=current_streak,
        best_streak=best_streak,
    )
