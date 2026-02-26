from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.repo.daily_runs_repo import DailyRunsRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.game.sessions.errors import SessionNotFoundError
from app.game.sessions.types import DailyRunSummary

from .constants import DAILY_CHALLENGE_TOTAL_QUESTIONS


async def abandon_session(
    session: AsyncSession,
    *,
    user_id: int,
    session_id: UUID,
    now_utc: datetime,
) -> None:
    quiz_session = await QuizSessionsRepo.get_by_id_for_update(session, session_id)
    if quiz_session is None or quiz_session.user_id != user_id:
        raise SessionNotFoundError
    if quiz_session.status != "STARTED":
        return

    quiz_session.status = "ABANDONED"
    quiz_session.completed_at = now_utc

    if quiz_session.source != "DAILY_CHALLENGE" or quiz_session.daily_run_id is None:
        return

    run = await DailyRunsRepo.get_by_id_for_update(session, quiz_session.daily_run_id)
    if run is None or run.status == "COMPLETED":
        return

    run.status = "ABANDONED"
    run.completed_at = None
    await emit_analytics_event(
        session,
        event_type="daily_abandoned",
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=user_id,
        payload={
            "daily_run_id": str(run.id),
            "berlin_date": run.berlin_date.isoformat(),
            "current_question": run.current_question,
            "score": run.score,
        },
    )


async def get_daily_run_summary(
    session: AsyncSession,
    *,
    user_id: int,
    daily_run_id: UUID,
) -> DailyRunSummary:
    run = await DailyRunsRepo.get_by_id(session, daily_run_id)
    if run is None or run.user_id != user_id:
        raise SessionNotFoundError
    return DailyRunSummary(
        daily_run_id=run.id,
        berlin_date=run.berlin_date,
        score=run.score,
        total_questions=DAILY_CHALLENGE_TOTAL_QUESTIONS,
        status=run.status,
    )
