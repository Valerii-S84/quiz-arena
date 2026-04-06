from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analytics_events import AnalyticsEvent
from app.db.models.purchases import Purchase

STAR_TO_EUR_RATE = Decimal("0.02")


def build_kpi(*, current: float, previous: float) -> dict[str, float]:
    if previous <= 0:
        delta = 100.0 if current > 0 else 0.0
    else:
        delta = ((current - previous) / previous) * 100
    return {
        "current": current,
        "previous": previous,
        "delta_pct": round(delta, 2),
    }


async def count_purchase_users(
    session: AsyncSession,
    *,
    from_utc: datetime,
    to_utc: datetime,
) -> int:
    stmt = select(func.count(distinct(Purchase.user_id))).where(
        Purchase.paid_at.is_not(None),
        Purchase.paid_at >= from_utc,
        Purchase.paid_at < to_utc,
        Purchase.status.in_(("PAID_UNCREDITED", "CREDITED")),
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def count_first_purchase_users(
    session: AsyncSession,
    *,
    from_utc: datetime,
    to_utc: datetime,
) -> int:
    first_purchase_by_user = (
        select(
            Purchase.user_id.label("user_id"),
            func.min(Purchase.paid_at).label("first_paid_at"),
        )
        .where(
            Purchase.paid_at.is_not(None),
            Purchase.status.in_(("PAID_UNCREDITED", "CREDITED")),
        )
        .group_by(Purchase.user_id)
        .subquery()
    )
    stmt = select(func.count(first_purchase_by_user.c.user_id)).where(
        first_purchase_by_user.c.first_paid_at >= from_utc,
        first_purchase_by_user.c.first_paid_at < to_utc,
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def sum_revenue_stars(
    session: AsyncSession,
    *,
    from_utc: datetime,
    to_utc: datetime,
) -> int:
    stmt = select(func.coalesce(func.sum(Purchase.stars_amount), 0)).where(
        Purchase.paid_at.is_not(None),
        Purchase.paid_at >= from_utc,
        Purchase.paid_at < to_utc,
        Purchase.status.in_(("PAID_UNCREDITED", "CREDITED")),
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def count_distinct_event_users(
    session: AsyncSession,
    *,
    event_type: str,
    from_utc: datetime,
    to_utc: datetime,
) -> int:
    stmt = select(func.count(distinct(AnalyticsEvent.user_id))).where(
        AnalyticsEvent.user_id.is_not(None),
        AnalyticsEvent.event_type == event_type,
        AnalyticsEvent.happened_at >= from_utc,
        AnalyticsEvent.happened_at < to_utc,
    )
    return int((await session.execute(stmt)).scalar_one() or 0)
