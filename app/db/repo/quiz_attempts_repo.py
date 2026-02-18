from __future__ import annotations

from datetime import datetime

from sqlalchemy import Date, cast, distinct, func, select
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

    @staticmethod
    async def count_user_attempts_between(
        session: AsyncSession,
        *,
        user_id: int,
        from_utc: datetime,
        to_utc: datetime,
    ) -> int:
        stmt = select(func.count(QuizAttempt.id)).where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.answered_at >= from_utc,
            QuizAttempt.answered_at < to_utc,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_user_active_local_days_between(
        session: AsyncSession,
        *,
        user_id: int,
        from_utc: datetime,
        to_utc: datetime,
    ) -> int:
        local_day_expr = cast(func.timezone("Europe/Berlin", QuizAttempt.answered_at), Date)
        stmt = select(func.count(distinct(local_day_expr))).where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.answered_at >= from_utc,
            QuizAttempt.answered_at < to_utc,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)
