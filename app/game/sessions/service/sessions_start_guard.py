from __future__ import annotations

from datetime import date, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.quiz_questions_repo import QuizQuestionsRepo
from app.game.questions.types import QuizQuestion
from app.game.sessions.errors import QuestionModeMismatchError

from .sessions_start_events import emit_question_mode_mismatch_event

logger = structlog.get_logger("app.game.sessions.start_guard")

_MENU_SOURCE = "MENU"
_MENU_MODE_MISMATCH_ALLOWED_MODES: frozenset[str] = frozenset()
(
    _REASON_NONE,
    _REASON_SELECTOR_FOREIGN_MODE,
    _REASON_RETRY_FOREIGN_MODE,
    _REASON_FALLBACK_FOREIGN_MODE,
) = (
    "none",
    "selector_returned_foreign_mode",
    "retry_returned_foreign_mode",
    "fallback_returned_foreign_mode",
)


def _is_guard_scope(*, mode_code: str, source: str) -> bool:
    return source == _MENU_SOURCE and mode_code not in _MENU_MODE_MISMATCH_ALLOWED_MODES


async def _resolve_served_question_mode(
    session: AsyncSession,
    *,
    mode_code: str,
    question: QuizQuestion,
    cache: dict[str, str],
) -> str:
    if question.mode_code is not None:
        return question.mode_code
    cached_mode = cache.get(question.question_id)
    if cached_mode is not None:
        return cached_mode
    record = await QuizQuestionsRepo.get_by_id(session, question.question_id)
    if record is None:
        cache[question.question_id] = mode_code
        return mode_code
    cache[question.question_id] = record.mode_code
    return record.mode_code


async def enforce_menu_served_mode_guard(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    source: str,
    question: QuizQuestion,
    local_date_berlin: date,
    recent_question_ids: list[str],
    selection_seed: str,
    preferred_level: str | None,
    now_utc: datetime,
) -> tuple[QuizQuestion, str, str, int, str]:
    served_mode_cache: dict[str, str] = {}
    served_question_mode = await _resolve_served_question_mode(
        session,
        mode_code=mode_code,
        question=question,
        cache=served_mode_cache,
    )
    if not _is_guard_scope(mode_code=mode_code, source=source) or served_question_mode == mode_code:
        return question, "none", served_question_mode, 0, _REASON_NONE

    logger.error(
        "question_mode_mismatch_detected",
        user_id=user_id,
        mode_code=mode_code,
        source=source,
        served_question_mode=served_question_mode,
        question_id=question.question_id,
        fallback_step="initial",
        retry_count=0,
        mismatch_reason=_REASON_SELECTOR_FOREIGN_MODE,
    )
    await emit_question_mode_mismatch_event(
        session,
        user_id=user_id,
        mode_code=mode_code,
        source=source,
        expected_level=preferred_level,
        served_level=question.level,
        served_question_mode=served_question_mode,
        question_id=question.question_id,
        fallback_step="initial",
        retry_count=0,
        mismatch_reason=_REASON_SELECTOR_FOREIGN_MODE,
        now_utc=now_utc,
    )

    from app.game.sessions import service as service_module

    retried_question = await service_module.select_question_for_mode(
        session,
        mode_code,
        local_date_berlin=local_date_berlin,
        recent_question_ids=recent_question_ids,
        selection_seed=f"{selection_seed}:mode_guard_retry",
        preferred_level=preferred_level,
    )
    retry_served_mode = await _resolve_served_question_mode(
        session,
        mode_code=mode_code,
        question=retried_question,
        cache=served_mode_cache,
    )
    if retry_served_mode == mode_code:
        return retried_question, "mode_retry", retry_served_mode, 1, _REASON_SELECTOR_FOREIGN_MODE

    logger.error(
        "question_mode_mismatch_detected",
        user_id=user_id,
        mode_code=mode_code,
        source=source,
        served_question_mode=retry_served_mode,
        question_id=retried_question.question_id,
        fallback_step="retry",
        retry_count=1,
        mismatch_reason=_REASON_RETRY_FOREIGN_MODE,
    )
    await emit_question_mode_mismatch_event(
        session,
        user_id=user_id,
        mode_code=mode_code,
        source=source,
        expected_level=preferred_level,
        served_level=retried_question.level,
        served_question_mode=retry_served_mode,
        question_id=retried_question.question_id,
        fallback_step="retry",
        retry_count=1,
        mismatch_reason=_REASON_RETRY_FOREIGN_MODE,
        now_utc=now_utc,
    )

    fallback_question = await service_module.get_question_for_mode(
        session,
        mode_code,
        local_date_berlin=local_date_berlin,
    )
    fallback_served_mode = await _resolve_served_question_mode(
        session,
        mode_code=mode_code,
        question=fallback_question,
        cache=served_mode_cache,
    )
    if fallback_served_mode != mode_code:
        logger.error(
            "question_mode_mismatch_unrecoverable",
            user_id=user_id,
            mode_code=mode_code,
            source=source,
            served_question_mode=fallback_served_mode,
            question_id=fallback_question.question_id,
            fallback_step="static_fallback_failed",
            retry_count=1,
            mismatch_reason=_REASON_FALLBACK_FOREIGN_MODE,
        )
        await emit_question_mode_mismatch_event(
            session,
            user_id=user_id,
            mode_code=mode_code,
            source=source,
            expected_level=preferred_level,
            served_level=fallback_question.level,
            served_question_mode=fallback_served_mode,
            question_id=fallback_question.question_id,
            fallback_step="static_fallback_failed",
            retry_count=1,
            mismatch_reason=_REASON_FALLBACK_FOREIGN_MODE,
            now_utc=now_utc,
        )
        raise QuestionModeMismatchError
    return fallback_question, "static_fallback", fallback_served_mode, 1, _REASON_RETRY_FOREIGN_MODE
