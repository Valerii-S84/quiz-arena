from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_sessions import QuizSession


class QuizAttemptsRepo:
    @staticmethod
    async def get_by_idempotency_key(session: AsyncSession, idempotency_key: str) -> QuizAttempt | None:
        stmt = select(QuizAttempt).where(QuizAttempt.idempotency_key == idempotency_key)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, *, attempt: QuizAttempt) -> QuizAttempt:
        session.add(attempt)
        await session.flush()
        return attempt

    @staticmethod
    async def get_recent_question_ids_for_mode(
        session: AsyncSession,
        *,
        user_id: int,
        mode_code: str,
        limit: int = 20,
    ) -> list[str]:
        stmt = (
            select(QuizAttempt.question_id)
            .join(QuizSession, QuizAttempt.session_id == QuizSession.id)
            .where(
                QuizAttempt.user_id == user_id,
                QuizSession.mode_code == mode_code,
            )
            .order_by(QuizAttempt.answered_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
