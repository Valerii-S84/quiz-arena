from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.economy.streak.service import StreakService
from app.game.sessions.types import AnswerSessionResult

from .levels import _is_persistent_adaptive_mode
from .progression import check_and_advance
from .sessions_submit_daily import apply_daily_answer
from .sessions_submit_friend_challenge import _apply_friend_challenge_answer
from .sessions_submit_runtime_context import (
    RegularAnswerResolution,
    SubmittedAnswerState,
    build_answer_text_fields,
)


async def _build_daily_answer_result(
    session: AsyncSession,
    *,
    user_id: int,
    submitted_answer: SubmittedAnswerState,
    now_utc: datetime,
) -> AnswerSessionResult:
    daily_state = await apply_daily_answer(
        session,
        user_id=user_id,
        quiz_session=submitted_answer.quiz_session,
        is_correct=submitted_answer.is_correct,
        now_utc=now_utc,
    )
    answer_text = build_answer_text_fields(submitted_answer)
    return AnswerSessionResult(
        session_id=submitted_answer.quiz_session.id,
        question_id=submitted_answer.question.question_id,
        is_correct=submitted_answer.is_correct,
        current_streak=daily_state.current_streak,
        best_streak=daily_state.best_streak,
        idempotent_replay=False,
        mode_code=submitted_answer.quiz_session.mode_code,
        source=submitted_answer.quiz_session.source,
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
        selected_answer_text=answer_text.selected_answer_text,
        correct_answer_text=answer_text.correct_answer_text,
        question_level=answer_text.question_level,
    )


async def _resolve_next_preferred_level(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str | None,
    now_utc: datetime,
) -> str | None:
    if mode_code is None or not _is_persistent_adaptive_mode(mode_code=mode_code):
        return None

    advanced_level, _, _ = await check_and_advance(
        user_id=user_id,
        mode=mode_code,
        db=session,
        now_utc=now_utc,
    )
    return advanced_level


async def _resolve_regular_answer_result(
    session: AsyncSession,
    *,
    user_id: int,
    submitted_answer: SubmittedAnswerState,
    now_utc: datetime,
) -> RegularAnswerResolution:
    friend_snapshot, friend_round_completed, friend_waiting_for_opponent = (
        await _apply_friend_challenge_answer(
            session,
            quiz_session=submitted_answer.quiz_session,
            user_id=user_id,
            is_correct=submitted_answer.is_correct,
            now_utc=now_utc,
        )
    )
    streak_result = await StreakService.record_activity(
        session,
        user_id=user_id,
        activity_at_utc=now_utc,
    )
    next_preferred_level = await _resolve_next_preferred_level(
        session,
        user_id=user_id,
        mode_code=submitted_answer.quiz_session.mode_code,
        now_utc=now_utc,
    )
    return RegularAnswerResolution(
        friend_snapshot=friend_snapshot,
        friend_round_completed=friend_round_completed,
        friend_waiting_for_opponent=friend_waiting_for_opponent,
        current_streak=streak_result.current_streak,
        best_streak=streak_result.best_streak,
        next_preferred_level=next_preferred_level,
    )


async def _build_regular_answer_result(
    session: AsyncSession,
    *,
    user_id: int,
    submitted_answer: SubmittedAnswerState,
    now_utc: datetime,
) -> AnswerSessionResult:
    regular_answer = await _resolve_regular_answer_result(
        session,
        user_id=user_id,
        submitted_answer=submitted_answer,
        now_utc=now_utc,
    )
    answer_text = build_answer_text_fields(submitted_answer)
    return AnswerSessionResult(
        session_id=submitted_answer.quiz_session.id,
        question_id=submitted_answer.question.question_id,
        is_correct=submitted_answer.is_correct,
        current_streak=regular_answer.current_streak,
        best_streak=regular_answer.best_streak,
        idempotent_replay=False,
        mode_code=submitted_answer.quiz_session.mode_code,
        source=submitted_answer.quiz_session.source,
        next_preferred_level=regular_answer.next_preferred_level,
        friend_challenge=regular_answer.friend_snapshot,
        friend_challenge_answered_round=submitted_answer.quiz_session.friend_challenge_round,
        friend_challenge_round_completed=regular_answer.friend_round_completed,
        friend_challenge_waiting_for_opponent=regular_answer.friend_waiting_for_opponent,
        selected_answer_text=answer_text.selected_answer_text,
        correct_answer_text=answer_text.correct_answer_text,
        question_level=answer_text.question_level,
    )


async def build_submitted_answer_result(
    session: AsyncSession,
    *,
    user_id: int,
    submitted_answer: SubmittedAnswerState,
    now_utc: datetime,
) -> AnswerSessionResult:
    if submitted_answer.quiz_session.source == "DAILY_CHALLENGE":
        return await _build_daily_answer_result(
            session,
            user_id=user_id,
            submitted_answer=submitted_answer,
            now_utc=now_utc,
        )
    return await _build_regular_answer_result(
        session,
        user_id=user_id,
        submitted_answer=submitted_answer,
        now_utc=now_utc,
    )
