from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.referrals import Referral


class ReferralsRepo:
    @staticmethod
    async def get_by_referred_user_id(
        session: AsyncSession,
        *,
        referred_user_id: int,
    ) -> Referral | None:
        stmt = select(Referral).where(Referral.referred_user_id == referred_user_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    async def create(session: AsyncSession, *, referral: Referral) -> Referral:
        session.add(referral)
        await session.flush()
        return referral

    @staticmethod
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

    @staticmethod
    async def get_by_id_for_update(
        session: AsyncSession,
        *,
        referral_id: int,
    ) -> Referral | None:
        stmt = select(Referral).where(Referral.id == referral_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    async def count_started_since(
        session: AsyncSession,
        *,
        since_utc: datetime,
    ) -> int:
        stmt = select(func.count(Referral.id)).where(Referral.created_at >= since_utc)
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
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

    @staticmethod
    async def list_referrer_stats_since(
        session: AsyncSession,
        *,
        since_utc: datetime,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        rejected_count = func.sum(
            case((Referral.status == "REJECTED_FRAUD", 1), else_=0)
        ).label("rejected_count")
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
            .order_by(rejected_count.desc(), total_count.desc(), Referral.referrer_user_id.asc())
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

    @staticmethod
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
        for referral_id, referrer_user_id, referred_user_id, fraud_score, created_at, status in result.all():
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

    @staticmethod
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
        stmt = stmt.order_by(Referral.fraud_score.desc(), Referral.created_at.desc(), Referral.id.desc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())
