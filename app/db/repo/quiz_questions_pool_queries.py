from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_questions import QuizQuestion
from app.db.repo.quiz_questions_types import QuizQuestionPoolCandidate, QuizQuestionPoolChange


def _candidate_from_row(row: Any) -> QuizQuestionPoolCandidate:
    (
        question_id,
        level,
        source_file,
        category,
        question_text,
        option_1,
        option_2,
        option_3,
        option_4,
        correct_option_id,
    ) = row
    return QuizQuestionPoolCandidate(
        question_id=question_id,
        level=level,
        source_file=source_file,
        category=category,
        question_text=question_text,
        option_1=option_1,
        option_2=option_2,
        option_3=option_3,
        option_4=option_4,
        correct_option_id=correct_option_id,
    )


def _candidate_select():
    return select(
        QuizQuestion.question_id,
        QuizQuestion.level,
        QuizQuestion.source_file,
        QuizQuestion.category,
        QuizQuestion.question_text,
        QuizQuestion.option_1,
        QuizQuestion.option_2,
        QuizQuestion.option_3,
        QuizQuestion.option_4,
        QuizQuestion.correct_option_id,
    )


async def list_question_candidates_for_mode(
    session: AsyncSession,
    *,
    mode_code: str,
    exclude_question_ids: Sequence[str] | None = None,
    preferred_levels: Sequence[str] | None = None,
) -> list[QuizQuestionPoolCandidate]:
    stmt = (
        _candidate_select()
        .where(
            QuizQuestion.mode_code == mode_code,
            QuizQuestion.status == "ACTIVE",
        )
        .order_by(QuizQuestion.question_id.asc())
    )
    if preferred_levels:
        stmt = stmt.where(QuizQuestion.level.in_(tuple(preferred_levels)))
    if exclude_question_ids:
        stmt = stmt.where(QuizQuestion.question_id.not_in(tuple(exclude_question_ids)))
    result = await session.execute(stmt)
    return [_candidate_from_row(row) for row in result.all()]


async def list_question_candidates_all_active(
    session: AsyncSession,
    *,
    exclude_question_ids: Sequence[str] | None = None,
    preferred_levels: Sequence[str] | None = None,
    require_quick_mix_eligible: bool = False,
) -> list[QuizQuestionPoolCandidate]:
    stmt = _candidate_select().where(QuizQuestion.status == "ACTIVE")
    stmt = stmt.order_by(QuizQuestion.question_id.asc())
    if require_quick_mix_eligible:
        stmt = stmt.where(QuizQuestion.quick_mix_eligible.is_(True))
    if preferred_levels:
        stmt = stmt.where(QuizQuestion.level.in_(tuple(preferred_levels)))
    if exclude_question_ids:
        stmt = stmt.where(QuizQuestion.question_id.not_in(tuple(exclude_question_ids)))
    result = await session.execute(stmt)
    return [_candidate_from_row(row) for row in result.all()]


def _pool_change_from_row(row: Any) -> QuizQuestionPoolChange:
    (
        question_id,
        mode_code,
        level,
        source_file,
        category,
        question_text,
        option_1,
        option_2,
        option_3,
        option_4,
        correct_option_id,
        status,
        quick_mix_eligible,
        updated_at,
    ) = row
    return QuizQuestionPoolChange(
        question_id=question_id,
        mode_code=mode_code,
        level=level,
        source_file=source_file,
        category=category,
        question_text=question_text,
        option_1=option_1,
        option_2=option_2,
        option_3=option_3,
        option_4=option_4,
        correct_option_id=correct_option_id,
        status=status,
        quick_mix_eligible=quick_mix_eligible,
        updated_at=updated_at,
    )


async def list_question_pool_changes_since(
    session: AsyncSession,
    *,
    since_updated_at: datetime,
) -> list[QuizQuestionPoolChange]:
    stmt = (
        select(
            QuizQuestion.question_id,
            QuizQuestion.mode_code,
            QuizQuestion.level,
            QuizQuestion.source_file,
            QuizQuestion.category,
            QuizQuestion.question_text,
            QuizQuestion.option_1,
            QuizQuestion.option_2,
            QuizQuestion.option_3,
            QuizQuestion.option_4,
            QuizQuestion.correct_option_id,
            QuizQuestion.status,
            QuizQuestion.quick_mix_eligible,
            QuizQuestion.updated_at,
        )
        .where(QuizQuestion.updated_at > since_updated_at)
        .order_by(QuizQuestion.updated_at.asc(), QuizQuestion.question_id.asc())
    )
    result = await session.execute(stmt)
    return [_pool_change_from_row(row) for row in result.all()]
