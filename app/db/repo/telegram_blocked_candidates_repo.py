from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.production_reliability import TelegramDeliveryAttempt


class TelegramBlockedCandidatesRepo:
    @staticmethod
    async def list_recent(
        session: AsyncSession,
        *,
        since_utc: datetime,
        limit: int,
        flow: str | None = None,
    ) -> list[TelegramDeliveryAttempt]:
        stmt = (
            select(TelegramDeliveryAttempt)
            .where(
                TelegramDeliveryAttempt.is_blocked_candidate.is_(True),
                TelegramDeliveryAttempt.created_at >= since_utc,
            )
            .order_by(
                TelegramDeliveryAttempt.created_at.desc(),
                TelegramDeliveryAttempt.id.desc(),
            )
            .limit(max(1, int(limit)))
        )
        if flow is not None:
            stmt = stmt.where(TelegramDeliveryAttempt.flow == flow)

        result = await session.execute(stmt)
        return list(result.scalars().all())
