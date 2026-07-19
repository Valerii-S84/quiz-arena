from __future__ import annotations

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.production_reliability import TelegramDeliveryAttempt


class TelegramDeliveryRetryRepo:
    @staticmethod
    async def claim_pending_batch(
        session: AsyncSession,
        *,
        flow: str,
        limit: int,
        claim_ttl_seconds: int = 300,
    ) -> list[TelegramDeliveryAttempt]:
        claim_age_seconds = func.extract("epoch", func.now() - TelegramDeliveryAttempt.updated_at)
        candidate_ids = (
            select(TelegramDeliveryAttempt.id)
            .where(
                TelegramDeliveryAttempt.flow == flow,
                TelegramDeliveryAttempt.status == "PENDING",
                or_(
                    TelegramDeliveryAttempt.attempt_count == 0,
                    claim_age_seconds >= max(1, int(claim_ttl_seconds)),
                ),
            )
            .order_by(
                TelegramDeliveryAttempt.created_at.asc(),
                TelegramDeliveryAttempt.id.asc(),
            )
            .limit(max(1, int(limit)))
            .with_for_update(skip_locked=True)
            .scalar_subquery()
        )
        stmt = (
            update(TelegramDeliveryAttempt)
            .where(TelegramDeliveryAttempt.id.in_(candidate_ids))
            .values(
                attempt_count=TelegramDeliveryAttempt.attempt_count + 1,
                updated_at=func.now(),
            )
            .returning(TelegramDeliveryAttempt)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
