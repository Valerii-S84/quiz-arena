from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime

from sqlalchemy import delete, distinct, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analytics_daily import AnalyticsDaily
from app.db.models.analytics_events import AnalyticsEvent
from app.db.models.promo_redemptions import PromoRedemption
from app.db.models.purchases import Purchase
from app.db.models.quiz_sessions import QuizSession
from app.db.models.users import User


@dataclass(frozen=True, slots=True)
class AnalyticsDailyUpsert:
    local_date_berlin: date
    dau: int
    wau: int
    mau: int
    purchases_credited_total: int
    purchasers_total: int
    purchase_rate: float
    promo_redemptions_total: int
    promo_redemptions_applied_total: int
    promo_redemption_rate: float
    promo_to_paid_conversions_total: int
    quiz_sessions_started_total: int
    quiz_sessions_completed_total: int
    gameplay_completion_rate: float
    energy_zero_events_total: int
    streak_lost_events_total: int
    referral_reward_milestone_events_total: int
    referral_reward_granted_events_total: int
    purchase_init_events_total: int
    purchase_invoice_sent_events_total: int
    purchase_precheckout_ok_events_total: int
    purchase_paid_uncredited_events_total: int
    purchase_credited_events_total: int
    calculated_at: datetime


class AnalyticsRepo:
    @staticmethod
    async def create_event(
        session: AsyncSession,
        *,
        event_type: str,
        source: str,
        user_id: int | None,
        local_date_berlin: date,
        payload: dict[str, object],
        happened_at: datetime,
    ) -> AnalyticsEvent:
        event = AnalyticsEvent(
            event_type=event_type,
            source=source,
            user_id=user_id,
            local_date_berlin=local_date_berlin,
            payload=payload,
            happened_at=happened_at,
        )
        session.add(event)
        await session.flush()
        return event

    @staticmethod
    async def count_distinct_active_users_between(
        session: AsyncSession,
        *,
        from_utc: datetime,
        to_utc: datetime,
    ) -> int:
        stmt = select(func.count(distinct(User.id))).where(
            User.last_seen_at.is_not(None),
            User.last_seen_at >= from_utc,
            User.last_seen_at < to_utc,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_credited_purchases_between(
        session: AsyncSession,
        *,
        from_utc: datetime,
        to_utc: datetime,
    ) -> int:
        stmt = select(func.count(Purchase.id)).where(
            Purchase.status == "CREDITED",
            Purchase.credited_at.is_not(None),
            Purchase.credited_at >= from_utc,
            Purchase.credited_at < to_utc,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_distinct_credited_purchasers_between(
        session: AsyncSession,
        *,
        from_utc: datetime,
        to_utc: datetime,
    ) -> int:
        stmt = select(func.count(distinct(Purchase.user_id))).where(
            Purchase.status == "CREDITED",
            Purchase.credited_at.is_not(None),
            Purchase.credited_at >= from_utc,
            Purchase.credited_at < to_utc,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_promo_to_paid_conversions_between(
        session: AsyncSession,
        *,
        from_utc: datetime,
        to_utc: datetime,
    ) -> int:
        stmt = select(func.count(Purchase.id)).where(
            Purchase.status == "CREDITED",
            Purchase.applied_promo_code_id.is_not(None),
            Purchase.credited_at.is_not(None),
            Purchase.credited_at >= from_utc,
            Purchase.credited_at < to_utc,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_promo_redemptions_between(
        session: AsyncSession,
        *,
        from_utc: datetime,
        to_utc: datetime,
    ) -> int:
        stmt = select(func.count(PromoRedemption.id)).where(
            PromoRedemption.created_at >= from_utc,
            PromoRedemption.created_at < to_utc,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_applied_promo_redemptions_between(
        session: AsyncSession,
        *,
        from_utc: datetime,
        to_utc: datetime,
    ) -> int:
        stmt = select(func.count(PromoRedemption.id)).where(
            PromoRedemption.created_at >= from_utc,
            PromoRedemption.created_at < to_utc,
            PromoRedemption.status == "APPLIED",
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_quiz_sessions_started_between(
        session: AsyncSession,
        *,
        from_utc: datetime,
        to_utc: datetime,
    ) -> int:
        stmt = select(func.count(QuizSession.id)).where(
            QuizSession.started_at >= from_utc,
            QuizSession.started_at < to_utc,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_quiz_sessions_completed_between(
        session: AsyncSession,
        *,
        from_utc: datetime,
        to_utc: datetime,
    ) -> int:
        stmt = select(func.count(QuizSession.id)).where(
            QuizSession.status == "COMPLETED",
            QuizSession.completed_at.is_not(None),
            QuizSession.completed_at >= from_utc,
            QuizSession.completed_at < to_utc,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_events_by_type_between(
        session: AsyncSession,
        *,
        from_utc: datetime,
        to_utc: datetime,
        event_types: tuple[str, ...],
    ) -> dict[str, int]:
        if not event_types:
            return {}
        stmt = (
            select(AnalyticsEvent.event_type, func.count(AnalyticsEvent.id))
            .where(
                AnalyticsEvent.happened_at >= from_utc,
                AnalyticsEvent.happened_at < to_utc,
                AnalyticsEvent.event_type.in_(event_types),
            )
            .group_by(AnalyticsEvent.event_type)
        )
        result = await session.execute(stmt)
        return {str(event_type): int(total) for event_type, total in result.all()}

    @staticmethod
    async def upsert_daily(session: AsyncSession, *, row: AnalyticsDailyUpsert) -> None:
        values = asdict(row)
        stmt = insert(AnalyticsDaily).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[AnalyticsDaily.local_date_berlin],
            set_=values,
        )
        await session.execute(stmt)

    @staticmethod
    async def list_daily(
        session: AsyncSession,
        *,
        limit: int,
    ) -> list[AnalyticsDaily]:
        stmt = select(AnalyticsDaily).order_by(AnalyticsDaily.local_date_berlin.desc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def delete_events_created_before(
        session: AsyncSession,
        *,
        cutoff_utc: datetime,
        limit: int,
    ) -> int:
        resolved_limit = max(1, int(limit))
        candidate_ids = (
            select(AnalyticsEvent.id)
            .where(AnalyticsEvent.created_at < cutoff_utc)
            .order_by(AnalyticsEvent.created_at.asc(), AnalyticsEvent.id.asc())
            .limit(resolved_limit)
            .scalar_subquery()
        )
        stmt = (
            delete(AnalyticsEvent)
            .where(AnalyticsEvent.id.in_(candidate_ids))
            .returning(AnalyticsEvent.id)
        )
        result = await session.execute(stmt)
        return len(list(result.scalars()))
