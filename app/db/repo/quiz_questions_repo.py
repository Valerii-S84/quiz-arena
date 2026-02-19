from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_questions import QuizQuestion


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
    ) -> list[str]:
        stmt = (
            select(QuizQuestion.question_id)
            .where(
                QuizQuestion.mode_code == mode_code,
                QuizQuestion.status == "ACTIVE",
            )
            .order_by(QuizQuestion.question_id.asc())
        )
        if exclude_question_ids:
            stmt = stmt.where(QuizQuestion.question_id.not_in(tuple(exclude_question_ids)))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_question_ids_all_active(
        session: AsyncSession,
        *,
        exclude_question_ids: Sequence[str] | None = None,
    ) -> list[str]:
        stmt = (
            select(QuizQuestion.question_id)
            .where(QuizQuestion.status == "ACTIVE")
            .order_by(QuizQuestion.question_id.asc())
        )
        if exclude_question_ids:
            stmt = stmt.where(QuizQuestion.question_id.not_in(tuple(exclude_question_ids)))
        result = await session.execute(stmt)
        return list(result.scalars().all())
