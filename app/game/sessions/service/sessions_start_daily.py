from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.models.daily_runs import DailyRun
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.daily_runs_repo import DailyRunsRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.game.questions.types import QuizQuestion
from app.game.sessions.errors import DailyChallengeAlreadyPlayedError
from app.game.sessions.types import SessionQuestionView, StartSessionResult

from .constants import DAILY_CHALLENGE_TOTAL_QUESTIONS
from .daily_question_sets import ensure_daily_question_set
from .question_loading import _build_start_result_from_existing_session


async def _emit_daily_blocked(
    session: AsyncSession,
    *,
    user_id: int,
    berlin_date: date,
    now_utc: datetime,
) -> None:
    await emit_analytics_event(
        session,
        event_type="daily_blocked_already_played",
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=user_id,
        payload={"berlin_date": berlin_date.isoformat()},
    )


async def _create_or_resume_daily_run(
    session: AsyncSession,
    *,
    user_id: int,
    berlin_date: date,
    now_utc: datetime,
) -> tuple[DailyRun, bool]:
    existing = await DailyRunsRepo.get_by_user_date_for_update(
        session,
        user_id=user_id,
        berlin_date=berlin_date,
    )
    if existing is not None:
        if existing.status == "COMPLETED":
            await _emit_daily_blocked(
                session,
                user_id=user_id,
                berlin_date=berlin_date,
                now_utc=now_utc,
            )
            raise DailyChallengeAlreadyPlayedError
        if existing.status == "ABANDONED":
            existing.status = "IN_PROGRESS"
            existing.completed_at = None
        return existing, False

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
        if loaded.status == "COMPLETED":
            await _emit_daily_blocked(
                session,
                user_id=user_id,
                berlin_date=berlin_date,
                now_utc=now_utc,
            )
            raise DailyChallengeAlreadyPlayedError
        if loaded.status == "ABANDONED":
            loaded.status = "IN_PROGRESS"
            loaded.completed_at = None
        return loaded, False
    return created, True


async def _resolve_daily_question_for_position(
    session: AsyncSession,
    *,
    berlin_date: date,
    position: int,
) -> tuple[str, QuizQuestion]:
    question_ids = await ensure_daily_question_set(session, berlin_date=berlin_date)
    if not question_ids:
        raise DailyChallengeAlreadyPlayedError

    from app.game.sessions import service as service_module

    index = max(0, min(len(question_ids) - 1, position - 1))
    question_id = question_ids[index]
    question = await service_module.get_question_by_id(
        session,
        "DAILY_CHALLENGE",
        question_id=question_id,
        local_date_berlin=berlin_date,
    )
    if question is not None:
        return question_id, question

    fallback_question = await service_module.get_question_for_mode(
        session,
        "DAILY_CHALLENGE",
        local_date_berlin=berlin_date,
    )
    return fallback_question.question_id, fallback_question


async def start_daily_session(
    session: AsyncSession,
    *,
    user_id: int,
    idempotency_key: str,
    local_date: date,
    now_utc: datetime,
) -> StartSessionResult:
    run, started_now = await _create_or_resume_daily_run(
        session,
        user_id=user_id,
        berlin_date=local_date,
        now_utc=now_utc,
    )
    if run.current_question >= DAILY_CHALLENGE_TOTAL_QUESTIONS:
        run.status = "COMPLETED"
        if run.completed_at is None:
            run.completed_at = now_utc
        await _emit_daily_blocked(
            session,
            user_id=user_id,
            berlin_date=local_date,
            now_utc=now_utc,
        )
        raise DailyChallengeAlreadyPlayedError

    active_session = await QuizSessionsRepo.get_active_daily_session_for_run(
        session,
        daily_run_id=run.id,
    )
    if active_session is not None:
        return await _build_start_result_from_existing_session(
            session,
            existing=active_session,
            idempotent_replay=False,
        )

    question_number = run.current_question + 1
    total_questions = DAILY_CHALLENGE_TOTAL_QUESTIONS
    question_id, question = await _resolve_daily_question_for_position(
        session,
        berlin_date=local_date,
        position=question_number,
    )

    created = None
    try:
        created = await QuizSessionsRepo.create(
            session,
            quiz_session=QuizSession(
                id=uuid4(),
                user_id=user_id,
                mode_code="DAILY_CHALLENGE",
                source="DAILY_CHALLENGE",
                status="STARTED",
                energy_cost_total=0,
                question_id=question_id,
                daily_run_id=run.id,
                started_at=now_utc,
                local_date_berlin=local_date,
                idempotency_key=idempotency_key,
            ),
        )
    except IntegrityError:
        recovered = await QuizSessionsRepo.get_active_daily_session_for_run(
            session,
            daily_run_id=run.id,
        )
        if recovered is None:
            raise
        return await _build_start_result_from_existing_session(
            session,
            existing=recovered,
            idempotent_replay=False,
        )

    if started_now:
        await emit_analytics_event(
            session,
            event_type="daily_started",
            source=EVENT_SOURCE_BOT,
            happened_at=now_utc,
            user_id=user_id,
            payload={
                "daily_run_id": str(run.id),
                "berlin_date": local_date.isoformat(),
            },
        )

    return StartSessionResult(
        session=SessionQuestionView(
            session_id=created.id,
            question_id=question.question_id,
            text=question.text,
            options=question.options,
            mode_code="DAILY_CHALLENGE",
            source="DAILY_CHALLENGE",
            category=question.category,
            question_number=question_number,
            total_questions=total_questions,
        ),
        energy_free=0,
        energy_paid=0,
        idempotent_replay=False,
    )
