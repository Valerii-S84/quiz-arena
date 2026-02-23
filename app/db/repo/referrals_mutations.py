from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.referrals import Referral


async def create(session: AsyncSession, *, referral: Referral) -> Referral:
    session.add(referral)
    await session.flush()
    return referral


async def mark_started_as_rejected_fraud(
    session: AsyncSession,
    *,
    referrer_user_id: int,
    min_created_at_utc: datetime,
    score: Decimal,
) -> int:
    stmt = (
        select(Referral)
        .where(
            Referral.referrer_user_id == referrer_user_id,
            Referral.status == "STARTED",
            Referral.created_at >= min_created_at_utc,
        )
        .with_for_update()
    )
    result = await session.execute(stmt)
    referrals = list(result.scalars().all())
    for referral in referrals:
        referral.status = "REJECTED_FRAUD"
        referral.fraud_score = score
    return len(referrals)
