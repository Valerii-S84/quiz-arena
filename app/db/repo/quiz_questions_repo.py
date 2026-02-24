from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_questions import QuizQuestion


@dataclass(frozen=True, slots=True)
class QuizQuestionPoolChange:
    question_id: str
    mode_code: str
    level: str
    status: str
    updated_at: datetime


class QuizQuestionsRepo:
    @staticmethod
    async def get_by_id(session: AsyncSession, question_id: str) -> QuizQuestion | None:
        return await session.get(QuizQuestion, question_id)

    @staticmethod
    async def list_question_ids_for_mode(
        session: AsyncSession,
        *,
        mode_code: str,
        exclude_question_ids: Sequence[str] | None = None,
        preferred_levels: Sequence[str] | None = None,
    ) -> list[str]:
        stmt = (
            select(QuizQuestion.question_id)
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
        return list(result.scalars().all())

    @staticmethod
    async def list_question_ids_all_active(
        session: AsyncSession,
        *,
        exclude_question_ids: Sequence[str] | None = None,
        preferred_levels: Sequence[str] | None = None,
    ) -> list[str]:
        stmt = (
            select(QuizQuestion.question_id)
            .where(QuizQuestion.status == "ACTIVE")
            .order_by(QuizQuestion.question_id.asc())
        )
        if preferred_levels:
            stmt = stmt.where(QuizQuestion.level.in_(tuple(preferred_levels)))
        if exclude_question_ids:
            stmt = stmt.where(QuizQuestion.question_id.not_in(tuple(exclude_question_ids)))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_by_ids(
        session: AsyncSession,
        *,
        question_ids: Sequence[str],
    ) -> list[QuizQuestion]:
        if not question_ids:
            return []
        stmt = select(QuizQuestion).where(
            QuizQuestion.question_id.in_(tuple(question_ids)),
            QuizQuestion.status == "ACTIVE",
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
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
                QuizQuestion.status,
                QuizQuestion.updated_at,
            )
            .where(QuizQuestion.updated_at > since_updated_at)
            .order_by(QuizQuestion.updated_at.asc(), QuizQuestion.question_id.asc())
        )
        result = await session.execute(stmt)
        return [
            QuizQuestionPoolChange(
                question_id=question_id,
                mode_code=mode_code,
                level=level,
                status=status,
                updated_at=updated_at,
            )
            for question_id, mode_code, level, status, updated_at in result.all()
        ]
