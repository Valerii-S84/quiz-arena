from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.quiz_attempts_repo import QuizAttemptsRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.game.sessions.errors import InvalidAnswerOptionError, SessionNotFoundError
from app.game.sessions.types import AnswerSessionResult

from .question_loading import _load_question_for_session
from .sessions_submit_replay import build_replay_answer_result
from .sessions_submit_runtime_context import AnswerSessionResolution, SubmittedAnswerState
from .sessions_submit_runtime_results import build_submitted_answer_result


def _validate_selected_option(selected_option: int) -> None:
    if selected_option < 0 or selected_option > 3:
        raise InvalidAnswerOptionError


async def _build_replay_result_for_attempt(
    session: AsyncSession,
    *,
    user_id: int,
    replay_session: QuizSession | None,
    replay_attempt,
    now_utc: datetime,
) -> AnswerSessionResult:
    return await build_replay_answer_result(
        session,
        user_id=user_id,
        replay_session=replay_session,
        replay_attempt=replay_attempt,
        now_utc=now_utc,
    )


async def _build_replay_resolution(
    session: AsyncSession,
    *,
    user_id: int,
    replay_session: QuizSession | None,
    replay_attempt,
    now_utc: datetime,
) -> AnswerSessionResolution:
    return AnswerSessionResolution(
        quiz_session=replay_session,
        replay_result=await _build_replay_result_for_attempt(
            session,
            user_id=user_id,
            replay_session=replay_session,
            replay_attempt=replay_attempt,
            now_utc=now_utc,
        ),
    )


async def _resolve_replay_result(
    session: AsyncSession,
    *,
    user_id: int,
    session_id: UUID,
    idempotency_key: str,
    now_utc: datetime,
) -> AnswerSessionResolution:
    existing_attempt = await QuizAttemptsRepo.get_by_idempotency_key(session, idempotency_key)
    if existing_attempt is not None:
        replay_session = await QuizSessionsRepo.get_by_id(session, existing_attempt.session_id)
        return await _build_replay_resolution(
            session,
            user_id=user_id,
            replay_session=replay_session,
            replay_attempt=existing_attempt,
            now_utc=now_utc,
        )

    quiz_session = await QuizSessionsRepo.get_by_id_for_update(session, session_id)
    if quiz_session is None or quiz_session.user_id != user_id:
        raise SessionNotFoundError

    if quiz_session.source == "DAILY_CHALLENGE" and quiz_session.status != "STARTED":
        replay_attempt = await QuizAttemptsRepo.get_latest_for_session(
            session,
            session_id=quiz_session.id,
        )
        return await _build_replay_resolution(
            session,
            user_id=user_id,
            replay_session=quiz_session,
            replay_attempt=replay_attempt,
            now_utc=now_utc,
        )

    return AnswerSessionResolution(quiz_session=quiz_session, replay_result=None)


async def _record_submitted_answer(
    session: AsyncSession,
    *,
    quiz_session: QuizSession,
    user_id: int,
    selected_option: int,
    idempotency_key: str,
    now_utc: datetime,
) -> SubmittedAnswerState:
    question = await _load_question_for_session(session, quiz_session=quiz_session)
    is_correct = selected_option == question.correct_option

    await QuizAttemptsRepo.create(
        session,
        attempt=QuizAttempt(
            session_id=quiz_session.id,
            user_id=user_id,
            question_id=question.question_id,
            is_correct=is_correct,
            answered_at=now_utc,
            response_ms=max(0, int((now_utc - quiz_session.started_at).total_seconds() * 1000)),
            idempotency_key=idempotency_key,
        ),
    )

    quiz_session.status = "COMPLETED"
    quiz_session.completed_at = now_utc
    return SubmittedAnswerState(
        quiz_session=quiz_session,
        question=question,
        is_correct=is_correct,
        selected_option=selected_option,
    )


async def submit_answer(
    session: AsyncSession,
    *,
    user_id: int,
    session_id: UUID,
    selected_option: int,
    idempotency_key: str,
    now_utc: datetime,
) -> AnswerSessionResult:
    _validate_selected_option(selected_option)
    session_resolution = await _resolve_replay_result(
        session,
        user_id=user_id,
        session_id=session_id,
        idempotency_key=idempotency_key,
        now_utc=now_utc,
    )
    if session_resolution.replay_result is not None:
        return session_resolution.replay_result
    assert session_resolution.quiz_session is not None

    submitted_answer = await _record_submitted_answer(
        session,
        quiz_session=session_resolution.quiz_session,
        user_id=user_id,
        selected_option=selected_option,
        idempotency_key=idempotency_key,
        now_utc=now_utc,
    )
    return await build_submitted_answer_result(
        session,
        user_id=user_id,
        submitted_answer=submitted_answer,
        now_utc=now_utc,
    )
