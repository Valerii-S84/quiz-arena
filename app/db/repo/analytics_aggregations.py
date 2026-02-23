from __future__ import annotations

from datetime import datetime

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analytics_events import AnalyticsEvent
from app.db.models.promo_redemptions import PromoRedemption
from app.db.models.purchases import Purchase
from app.db.models.quiz_sessions import QuizSession
from app.db.models.users import User


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
