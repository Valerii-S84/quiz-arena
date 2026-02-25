from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_attempts import QuizAttempt
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.quiz_attempts_repo import QuizAttemptsRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.economy.streak.service import StreakService
from app.game.sessions.errors import InvalidAnswerOptionError, SessionNotFoundError
from app.game.sessions.types import AnswerSessionResult

from .friend_challenges_internal import _build_friend_challenge_snapshot
from .levels import _is_persistent_adaptive_mode
from .progression import check_and_advance
from .question_loading import _load_question_for_session
from .sessions_submit_friend_challenge import _apply_friend_challenge_answer


async def submit_answer(
    session: AsyncSession,
    *,
    user_id: int,
    session_id: UUID,
    selected_option: int,
    idempotency_key: str,
    now_utc: datetime,
) -> AnswerSessionResult:
    if selected_option < 0 or selected_option > 3:
        raise InvalidAnswerOptionError

    existing_attempt = await QuizAttemptsRepo.get_by_idempotency_key(session, idempotency_key)
    if existing_attempt is not None:
        streak_snapshot = await StreakService.sync_rollover(
            session,
            user_id=user_id,
            now_utc=now_utc,
        )
        replay_session = await QuizSessionsRepo.get_by_id(session, existing_attempt.session_id)
        friend_snapshot = None
        waiting_for_opponent = False
        if replay_session is not None and replay_session.friend_challenge_id is not None:
            challenge = await FriendChallengesRepo.get_by_id(
                session, replay_session.friend_challenge_id
            )
            if challenge is not None:
                friend_snapshot = _build_friend_challenge_snapshot(challenge)
                waiting_for_opponent = challenge.status == "ACTIVE"
        return AnswerSessionResult(
            session_id=existing_attempt.session_id,
            question_id=existing_attempt.question_id,
            is_correct=existing_attempt.is_correct,
            current_streak=streak_snapshot.current_streak,
            best_streak=streak_snapshot.best_streak,
            idempotent_replay=True,
            mode_code=(replay_session.mode_code if replay_session is not None else None),
            source=replay_session.source if replay_session is not None else None,
            selected_answer_text=None,
            correct_answer_text=None,
            question_level=None,
            next_preferred_level=None,
            friend_challenge=friend_snapshot,
            friend_challenge_answered_round=(
                replay_session.friend_challenge_round if replay_session is not None else None
            ),
            friend_challenge_round_completed=False,
            friend_challenge_waiting_for_opponent=waiting_for_opponent,
        )

    quiz_session = await QuizSessionsRepo.get_by_id_for_update(session, session_id)
    if quiz_session is None or quiz_session.user_id != user_id:
        raise SessionNotFoundError

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
            response_ms=0,
            idempotency_key=idempotency_key,
        ),
    )

    quiz_session.status = "COMPLETED"
    quiz_session.completed_at = now_utc

    friend_snapshot, friend_round_completed, friend_waiting_for_opponent = (
        await _apply_friend_challenge_answer(
            session,
            quiz_session=quiz_session,
            user_id=user_id,
            is_correct=is_correct,
            now_utc=now_utc,
        )
    )

    streak_result = await StreakService.record_activity(
        session,
        user_id=user_id,
        activity_at_utc=now_utc,
    )
    next_preferred_level = None
    if _is_persistent_adaptive_mode(mode_code=quiz_session.mode_code):
        advanced_level, _, _ = await check_and_advance(
            user_id=user_id,
            mode=quiz_session.mode_code,
            db=session,
            now_utc=now_utc,
        )
        next_preferred_level = advanced_level

    return AnswerSessionResult(
        session_id=quiz_session.id,
        question_id=question.question_id,
        is_correct=is_correct,
        current_streak=streak_result.current_streak,
        best_streak=streak_result.best_streak,
        idempotent_replay=False,
        mode_code=quiz_session.mode_code,
        source=quiz_session.source,
        selected_answer_text=question.options[selected_option],
        correct_answer_text=question.options[question.correct_option],
        question_level=question.level,
        next_preferred_level=next_preferred_level,
        friend_challenge=friend_snapshot,
        friend_challenge_answered_round=quiz_session.friend_challenge_round,
        friend_challenge_round_completed=friend_round_completed,
        friend_challenge_waiting_for_opponent=friend_waiting_for_opponent,
    )
