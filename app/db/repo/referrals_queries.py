from __future__ import annotations

from datetime import datetime

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.referrals import Referral


async def get_by_referred_user_id(
    session: AsyncSession,
    *,
    referred_user_id: int,
) -> Referral | None:
    stmt = select(Referral).where(Referral.referred_user_id == referred_user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_reverse_pair_since(
    session: AsyncSession,
    *,
    referrer_user_id: int,
    referred_user_id: int,
    since_utc: datetime,
) -> Referral | None:
    stmt = select(Referral).where(
        Referral.referrer_user_id == referred_user_id,
        Referral.referred_user_id == referrer_user_id,
        Referral.created_at >= since_utc,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_started_ids(
    session: AsyncSession,
    *,
    limit: int = 200,
) -> list[int]:
    stmt = (
        select(Referral.id)
        .where(Referral.status == "STARTED")
        .order_by(Referral.created_at.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_by_id_for_update(
    session: AsyncSession,
    *,
    referral_id: int,
) -> Referral | None:
    stmt = select(Referral).where(Referral.id == referral_id).with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_referrer_ids_with_reward_candidates(
    session: AsyncSession,
    *,
    qualified_before_utc: datetime,
    limit: int = 200,
) -> list[int]:
    stmt = (
        select(distinct(Referral.referrer_user_id))
        .where(
            Referral.status.in_(("QUALIFIED", "DEFERRED_LIMIT")),
            Referral.qualified_at.is_not(None),
            Referral.qualified_at <= qualified_before_utc,
        )
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [int(user_id) for user_id in result.scalars().all()]


async def list_for_referrer_for_update(
    session: AsyncSession,
    *,
    referrer_user_id: int,
) -> list[Referral]:
    stmt = (
        select(Referral)
        .where(
            Referral.referrer_user_id == referrer_user_id,
            Referral.status.in_(("QUALIFIED", "DEFERRED_LIMIT", "REWARDED", "REJECTED_FRAUD")),
        )
        .order_by(Referral.qualified_at.asc().nulls_last(), Referral.created_at.asc())
        .with_for_update()
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_for_referrer(
    session: AsyncSession,
    *,
    referrer_user_id: int,
) -> list[Referral]:
    stmt = (
        select(Referral)
        .where(
            Referral.referrer_user_id == referrer_user_id,
            Referral.status.in_(("QUALIFIED", "DEFERRED_LIMIT", "REWARDED", "REJECTED_FRAUD")),
        )
        .order_by(Referral.qualified_at.asc().nulls_last(), Referral.created_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_for_review_since(
    session: AsyncSession,
    *,
    since_utc: datetime,
    status: str | None = None,
    limit: int = 100,
) -> list[Referral]:
    stmt = select(Referral).where(Referral.created_at >= since_utc)
    if status is not None:
        stmt = stmt.where(Referral.status == status)
    stmt = stmt.order_by(
        Referral.fraud_score.desc(), Referral.created_at.desc(), Referral.id.desc()
    ).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())
