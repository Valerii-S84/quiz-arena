from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.daily_runs import DailyRun
from app.db.repo.daily_runs_repo import DailyRunsRepo
from app.game.sessions.errors import DailyChallengeAlreadyPlayedError


def _resume_daily_run_if_needed(run: DailyRun) -> DailyRun:
    if run.status == "ABANDONED":
        run.status = "IN_PROGRESS"
        run.completed_at = None
    return run


async def _raise_if_daily_run_completed(
    session: AsyncSession,
    *,
    run: DailyRun,
    user_id: int,
    berlin_date: date,
    now_utc: datetime,
    emit_daily_blocked: Callable[..., Awaitable[None]],
) -> None:
    if run.status != "COMPLETED":
        return
    await emit_daily_blocked(
        session,
        user_id=user_id,
        berlin_date=berlin_date,
        now_utc=now_utc,
    )
    raise DailyChallengeAlreadyPlayedError


async def create_or_resume_daily_run(
    session: AsyncSession,
    *,
    user_id: int,
    berlin_date: date,
    now_utc: datetime,
    emit_daily_blocked: Callable[..., Awaitable[None]],
) -> tuple[DailyRun, bool]:
    existing = await DailyRunsRepo.get_by_user_date_for_update(
        session,
        user_id=user_id,
        berlin_date=berlin_date,
    )
    if existing is not None:
        await _raise_if_daily_run_completed(
            session,
            run=existing,
            user_id=user_id,
            berlin_date=berlin_date,
            now_utc=now_utc,
            emit_daily_blocked=emit_daily_blocked,
        )
        return _resume_daily_run_if_needed(existing), False

    run = DailyRun(
        id=uuid4(),
        user_id=user_id,
        berlin_date=berlin_date,
        current_question=0,
        score=0,
        status="IN_PROGRESS",
        started_at=now_utc,
        completed_at=None,
    )
    try:
        created = await DailyRunsRepo.create(session, daily_run=run)
    except IntegrityError:
        loaded = await DailyRunsRepo.get_by_user_date_for_update(
            session,
            user_id=user_id,
            berlin_date=berlin_date,
        )
        if loaded is None:
            raise
        await _raise_if_daily_run_completed(
            session,
            run=loaded,
            user_id=user_id,
            berlin_date=berlin_date,
            now_utc=now_utc,
            emit_daily_blocked=emit_daily_blocked,
        )
        return _resume_daily_run_if_needed(loaded), False
    return created, True
