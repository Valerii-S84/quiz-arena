from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.daily_push_logs import DailyPushLog


class DailyPushLogsRepo:
    @staticmethod
    async def create_once(
        session: AsyncSession,
        *,
        user_id: int,
        berlin_date: date,
        push_sent_at: datetime,
    ) -> bool:
        stmt = (
            insert(DailyPushLog)
            .values(
                user_id=user_id,
                berlin_date=berlin_date,
                push_sent_at=push_sent_at,
            )
            .on_conflict_do_nothing(index_elements=[DailyPushLog.user_id, DailyPushLog.berlin_date])
            .returning(DailyPushLog.user_id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None
