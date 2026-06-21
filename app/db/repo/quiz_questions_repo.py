from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_questions import QuizQuestion
from app.db.repo.quiz_questions_pool_queries import (
    list_question_candidates_all_active as _list_question_candidates_all_active,
)
from app.db.repo.quiz_questions_pool_queries import (
    list_question_candidates_for_mode as _list_question_candidates_for_mode,
)
from app.db.repo.quiz_questions_pool_queries import (
    list_question_pool_changes_since as _list_question_pool_changes_since,
)
from app.db.repo.quiz_questions_types import (  # noqa: F401
    QuizQuestionPoolCandidate,
    QuizQuestionPoolChange,
)


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
        require_quick_mix_eligible: bool = False,
    ) -> list[str]:
        stmt = (
            select(QuizQuestion.question_id)
            .where(QuizQuestion.status == "ACTIVE")
            .order_by(QuizQuestion.question_id.asc())
        )
        if require_quick_mix_eligible:
            stmt = stmt.where(QuizQuestion.quick_mix_eligible.is_(True))
        if preferred_levels:
            stmt = stmt.where(QuizQuestion.level.in_(tuple(preferred_levels)))
        if exclude_question_ids:
            stmt = stmt.where(QuizQuestion.question_id.not_in(tuple(exclude_question_ids)))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    list_question_candidates_for_mode = staticmethod(_list_question_candidates_for_mode)
    list_question_candidates_all_active = staticmethod(_list_question_candidates_all_active)

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

    list_question_pool_changes_since = staticmethod(_list_question_pool_changes_since)
