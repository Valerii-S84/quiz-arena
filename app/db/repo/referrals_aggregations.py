from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.referrals import Referral


async def count_referrer_starts_between(
    session: AsyncSession,
    *,
    referrer_user_id: int,
    from_utc: datetime,
    to_utc: datetime,
) -> int:
    stmt = select(func.count(Referral.id)).where(
        Referral.referrer_user_id == referrer_user_id,
        Referral.created_at >= from_utc,
        Referral.created_at < to_utc,
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def count_rewards_for_referrer_between(
    session: AsyncSession,
    *,
    referrer_user_id: int,
    from_utc: datetime,
    to_utc: datetime,
) -> int:
    stmt = select(func.count(Referral.id)).where(
        Referral.referrer_user_id == referrer_user_id,
        Referral.status == "REWARDED",
        Referral.rewarded_at.is_not(None),
        Referral.rewarded_at >= from_utc,
        Referral.rewarded_at < to_utc,
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def count_qualified_for_referrer(
    session: AsyncSession,
    *,
    referrer_user_id: int,
) -> int:
    stmt = select(func.count(Referral.id)).where(
        Referral.referrer_user_id == referrer_user_id,
        Referral.status.in_(("QUALIFIED", "DEFERRED_LIMIT", "REWARDED")),
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def count_rewarded_for_referrer(
    session: AsyncSession,
    *,
    referrer_user_id: int,
) -> int:
    stmt = select(func.count(Referral.id)).where(
        Referral.referrer_user_id == referrer_user_id,
        Referral.status == "REWARDED",
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def count_started_since(
    session: AsyncSession,
    *,
    since_utc: datetime,
) -> int:
    stmt = select(func.count(Referral.id)).where(Referral.created_at >= since_utc)
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def count_by_status_since(
    session: AsyncSession,
    *,
    since_utc: datetime,
) -> dict[str, int]:
    stmt = (
        select(Referral.status, func.count(Referral.id))
        .where(Referral.created_at >= since_utc)
        .group_by(Referral.status)
    )
    result = await session.execute(stmt)
    return {str(status): int(count) for status, count in result.all()}


async def list_referrer_stats_since(
    session: AsyncSession,
    *,
    since_utc: datetime,
    limit: int = 20,
) -> list[dict[str, object]]:
    rejected_count = func.sum(case((Referral.status == "REJECTED_FRAUD", 1), else_=0)).label(
        "rejected_count"
    )
    total_count = func.count(Referral.id).label("total_count")
    last_start_at = func.max(Referral.created_at).label("last_start_at")
    stmt = (
        select(
            Referral.referrer_user_id,
            total_count,
            rejected_count,
            last_start_at,
        )
        .where(Referral.created_at >= since_utc)
        .group_by(Referral.referrer_user_id)
        .order_by(
            rejected_count.desc(),
            total_count.desc(),
            Referral.referrer_user_id.asc(),
        )
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows: list[dict[str, object]] = []
    for referrer_user_id, total, rejected, last_at in result.all():
        rows.append(
            {
                "referrer_user_id": int(referrer_user_id),
                "started_total": int(total or 0),
                "rejected_fraud_total": int(rejected or 0),
                "last_start_at": last_at,
            }
        )
    return rows


async def list_recent_fraud_cases_since(
    session: AsyncSession,
    *,
    since_utc: datetime,
    limit: int = 50,
) -> list[dict[str, object]]:
    stmt = (
        select(
            Referral.id,
            Referral.referrer_user_id,
            Referral.referred_user_id,
            Referral.fraud_score,
            Referral.created_at,
            Referral.status,
        )
        .where(
            Referral.created_at >= since_utc,
            Referral.status == "REJECTED_FRAUD",
        )
        .order_by(Referral.created_at.desc(), Referral.id.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows: list[dict[str, object]] = []
    for (
        referral_id,
        referrer_user_id,
        referred_user_id,
        fraud_score,
        created_at,
        status,
    ) in result.all():
        rows.append(
            {
                "referral_id": int(referral_id),
                "referrer_user_id": int(referrer_user_id),
                "referred_user_id": int(referred_user_id),
                "fraud_score": float(fraud_score),
                "created_at": created_at,
                "status": str(status),
            }
        )
    return rows
