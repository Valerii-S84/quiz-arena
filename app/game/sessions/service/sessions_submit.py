from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_sessions import QuizSession
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
from .sessions_submit_daily import apply_daily_answer, build_daily_replay_state
from .sessions_submit_friend_challenge import _apply_friend_challenge_answer


async def _build_replay_answer_result(
    session: AsyncSession,
    *,
    user_id: int,
    replay_session: QuizSession | None,
    replay_attempt: QuizAttempt | None,
    now_utc: datetime,
) -> AnswerSessionResult:
    streak_snapshot = await StreakService.sync_rollover(
        session,
        user_id=user_id,
        now_utc=now_utc,
    )
    friend_snapshot = None
    waiting_for_opponent = False
    if replay_session is not None and replay_session.friend_challenge_id is not None:
        challenge = await FriendChallengesRepo.get_by_id(session, replay_session.friend_challenge_id)
        if challenge is not None:
            friend_snapshot = _build_friend_challenge_snapshot(challenge)
            waiting_for_opponent = challenge.status == "ACTIVE"

    daily_state = None
    if replay_session is not None and replay_session.source == "DAILY_CHALLENGE":
        daily_state = await build_daily_replay_state(
            session,
            replay_session=replay_session,
            current_streak=streak_snapshot.current_streak,
            best_streak=streak_snapshot.best_streak,
        )

    return AnswerSessionResult(
        session_id=(
            replay_attempt.session_id
            if replay_attempt is not None
            else replay_session.id
            if replay_session is not None
            else UUID(int=0)
        ),
        question_id=(
            replay_attempt.question_id
            if replay_attempt is not None
            else (replay_session.question_id or "")
            if replay_session is not None
            else ""
        ),
        is_correct=(replay_attempt.is_correct if replay_attempt is not None else False),
        current_streak=(
            daily_state.current_streak if daily_state is not None else streak_snapshot.current_streak
        ),
        best_streak=(
            daily_state.best_streak if daily_state is not None else streak_snapshot.best_streak
        ),
        idempotent_replay=True,
        mode_code=(replay_session.mode_code if replay_session is not None else None),
        source=(replay_session.source if replay_session is not None else None),
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
        daily_run_id=(daily_state.daily_run_id if daily_state is not None else None),
        daily_current_question=(daily_state.current_question if daily_state is not None else None),
        daily_total_questions=(daily_state.total_questions if daily_state is not None else None),
        daily_score=(daily_state.score if daily_state is not None else None),
        daily_completed=(daily_state.completed if daily_state is not None else False),
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
    if selected_option < 0 or selected_option > 3:
        raise InvalidAnswerOptionError

    existing_attempt = await QuizAttemptsRepo.get_by_idempotency_key(session, idempotency_key)
    if existing_attempt is not None:
        replay_session = await QuizSessionsRepo.get_by_id(session, existing_attempt.session_id)
        return await _build_replay_answer_result(
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
        return await _build_replay_answer_result(
            session,
            user_id=user_id,
            replay_session=quiz_session,
            replay_attempt=replay_attempt,
            now_utc=now_utc,
        )

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

    if quiz_session.source == "DAILY_CHALLENGE":
        daily_state = await apply_daily_answer(
            session,
            user_id=user_id,
            quiz_session=quiz_session,
            is_correct=is_correct,
            now_utc=now_utc,
        )
        return AnswerSessionResult(
            session_id=quiz_session.id,
            question_id=question.question_id,
            is_correct=is_correct,
            current_streak=daily_state.current_streak,
            best_streak=daily_state.best_streak,
            idempotent_replay=False,
            mode_code=quiz_session.mode_code,
            source=quiz_session.source,
            selected_answer_text=question.options[selected_option],
            correct_answer_text=question.options[question.correct_option],
            question_level=question.level,
            next_preferred_level=None,
            friend_challenge=None,
            friend_challenge_answered_round=None,
            friend_challenge_round_completed=False,
            friend_challenge_waiting_for_opponent=False,
            daily_run_id=daily_state.daily_run_id,
            daily_current_question=daily_state.current_question,
            daily_total_questions=daily_state.total_questions,
            daily_score=daily_state.score,
            daily_completed=daily_state.completed,
        )

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
