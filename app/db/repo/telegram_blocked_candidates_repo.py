from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.production_reliability import TelegramDeliveryAttempt
from app.db.models.users import User
from app.db.repo.production_reliability_types import DELIVERY_STATUS_FAILED


class TelegramBlockedCandidatesRepo:
    @staticmethod
    async def has_blocked_candidate(
        session: AsyncSession,
        *,
        telegram_user_id: int,
        blocked_since: datetime,
    ) -> bool:
        blocked_at = func.coalesce(
            TelegramDeliveryAttempt.failed_at,
            TelegramDeliveryAttempt.updated_at,
            TelegramDeliveryAttempt.created_at,
        )
        stmt = (
            select(TelegramDeliveryAttempt.id)
            .where(
                TelegramDeliveryAttempt.telegram_user_id == telegram_user_id,
                TelegramDeliveryAttempt.status == DELIVERY_STATUS_FAILED,
                TelegramDeliveryAttempt.is_blocked_candidate.is_(True),
                blocked_at >= blocked_since,
                ~select(User.id)
                .where(
                    User.telegram_user_id == telegram_user_id,
                    User.last_seen_at.is_not(None),
                    User.last_seen_at > blocked_at,
                )
                .exists(),
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None
