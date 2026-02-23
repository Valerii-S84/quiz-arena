from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_sessions import QuizSession
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.quiz_attempts_repo import QuizAttemptsRepo
from app.db.repo.quiz_questions_repo import QuizQuestionsRepo
from app.game.questions.types import QuizQuestion
from app.game.sessions.types import SessionQuestionView, StartSessionResult

from .levels import _normalize_level


async def _infer_preferred_level_from_recent_attempt(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
) -> str | None:
    recent_question_ids = await QuizAttemptsRepo.get_recent_question_ids_for_mode(
        session,
        user_id=user_id,
        mode_code=mode_code,
        limit=1,
    )
    if not recent_question_ids:
        return None

    latest_question = await QuizQuestionsRepo.get_by_id(session, recent_question_ids[0])
    if latest_question is None or latest_question.status != "ACTIVE":
        return None

    return _normalize_level(latest_question.level)


async def _load_question_for_session(
    session: AsyncSession,
    *,
    quiz_session: QuizSession,
) -> QuizQuestion:
    question = None
    if quiz_session.question_id is not None:
        from app.game.sessions import service as service_module

        question = await service_module.get_question_by_id(
            session,
            quiz_session.mode_code,
            question_id=quiz_session.question_id,
            local_date_berlin=quiz_session.local_date_berlin,
        )
    if question is not None:
        return question
    from app.game.sessions import service as service_module

    return await service_module.get_question_for_mode(
        session,
        quiz_session.mode_code,
        local_date_berlin=quiz_session.local_date_berlin,
    )


async def _build_start_result_from_existing_session(
    session: AsyncSession,
    *,
    existing: QuizSession,
    idempotent_replay: bool,
) -> StartSessionResult:
    question = await _load_question_for_session(session, quiz_session=existing)
    total_questions: int | None = None
    question_number: int | None = None
    if existing.source == "FRIEND_CHALLENGE":
        question_number = existing.friend_challenge_round
        if existing.friend_challenge_id is not None:
            challenge = await FriendChallengesRepo.get_by_id(session, existing.friend_challenge_id)
            if challenge is not None:
                total_questions = challenge.total_rounds
    return StartSessionResult(
        session=SessionQuestionView(
            session_id=existing.id,
            question_id=question.question_id,
            text=question.text,
            options=question.options,
            mode_code=existing.mode_code,
            source=existing.source,
            category=question.category,
            question_number=question_number,
            total_questions=total_questions,
        ),
        energy_free=0,
        energy_paid=0,
        idempotent_replay=idempotent_replay,
    )
