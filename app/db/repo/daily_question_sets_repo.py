from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.daily_question_sets import DailyQuestionSet


class DailyQuestionSetsRepo:
    @staticmethod
    async def list_question_ids_for_date(
        session: AsyncSession,
        *,
        berlin_date: date,
    ) -> tuple[str, ...]:
        stmt = (
            select(DailyQuestionSet.question_id)
            .where(DailyQuestionSet.berlin_date == berlin_date)
            .order_by(DailyQuestionSet.position.asc())
        )
        result = await session.execute(stmt)
        return tuple(result.scalars().all())

    @staticmethod
    async def get_question_id_for_position(
        session: AsyncSession,
        *,
        berlin_date: date,
        position: int,
    ) -> str | None:
        stmt = select(DailyQuestionSet.question_id).where(
            DailyQuestionSet.berlin_date == berlin_date,
            DailyQuestionSet.position == position,
        )
        result = await session.execute(stmt)
        value = result.scalar_one_or_none()
        return value if isinstance(value, str) else None

    @staticmethod
    async def upsert_question_ids(
        session: AsyncSession,
        *,
        berlin_date: date,
        question_ids: tuple[str, ...],
    ) -> None:
        if not question_ids:
            return
        values = [
            {
                "berlin_date": berlin_date,
                "position": position,
                "question_id": question_id,
            }
            for position, question_id in enumerate(question_ids, start=1)
        ]
        stmt = insert(DailyQuestionSet).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[DailyQuestionSet.berlin_date, DailyQuestionSet.position],
            set_={"question_id": stmt.excluded.question_id},
        )
        await session.execute(stmt)
