from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.purchases import Purchase
from app.db.models.users import User

STAR_TO_EUR_RATE = Decimal("0.02")


async def build_ltv_30d_by_cohort(
    session: AsyncSession,
    *,
    cohort_from_utc: datetime,
    cohort_to_utc: datetime,
) -> list[dict[str, object]]:
    cohort_expr = func.date_trunc("week", User.created_at)
    join_condition = and_(
        Purchase.user_id == User.id,
        Purchase.paid_at.is_not(None),
        Purchase.status.in_(("PAID_UNCREDITED", "CREDITED")),
        Purchase.paid_at >= User.created_at,
        Purchase.paid_at < (User.created_at + text("interval '30 days'")),
    )

    rows = (
        await session.execute(
            select(
                cohort_expr,
                func.count(distinct(User.id)),
                func.coalesce(func.sum(Purchase.stars_amount), 0),
            )
            .select_from(User)
            .outerjoin(Purchase, join_condition)
            .where(User.created_at >= cohort_from_utc, User.created_at < cohort_to_utc)
            .group_by(cohort_expr)
            .order_by(cohort_expr)
        )
    ).all()

    result: list[dict[str, object]] = []
    for cohort_dt, cohort_size_raw, revenue_stars_raw in rows:
        cohort_size = max(1, int(cohort_size_raw or 0))
        revenue_stars = int(revenue_stars_raw or 0)
        ltv_stars = round(revenue_stars / cohort_size, 2)
        ltv_eur = round(float((Decimal(revenue_stars) * STAR_TO_EUR_RATE) / cohort_size), 2)
        result.append(
            {
                "cohort_week": cohort_dt.date().isoformat(),
                "cohort_size": cohort_size,
                "revenue_stars_30d": revenue_stars,
                "ltv_stars_30d": ltv_stars,
                "ltv_eur_30d": ltv_eur,
            }
        )
    return result
