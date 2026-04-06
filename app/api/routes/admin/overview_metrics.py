from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import Integer, cast, distinct, func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analytics_events import AnalyticsEvent
from app.db.models.purchases import Purchase
from app.db.models.quiz_sessions import QuizSession
from app.db.models.users import User

BERLIN_TZ = ZoneInfo("Europe/Berlin")
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


def build_activity_days_subquery(*, from_utc: datetime, to_utc: datetime):
    return union_all(
        select(
            User.id.label("user_id"),
            func.date(func.timezone("Europe/Berlin", User.created_at)).label("local_date_berlin"),
        ).where(
            User.created_at >= from_utc,
            User.created_at < to_utc,
        ),
        select(
            AnalyticsEvent.user_id.label("user_id"),
            AnalyticsEvent.local_date_berlin.label("local_date_berlin"),
        ).where(
            AnalyticsEvent.user_id.is_not(None),
            AnalyticsEvent.happened_at >= from_utc,
            AnalyticsEvent.happened_at < to_utc,
        ),
        select(
            QuizSession.user_id.label("user_id"),
            QuizSession.local_date_berlin.label("local_date_berlin"),
        ).where(
            QuizSession.started_at >= from_utc,
            QuizSession.started_at < to_utc,
        ),
    ).subquery()


async def count_distinct_users(
    session: AsyncSession,
    *,
    from_utc: datetime,
    to_utc: datetime,
) -> int:
    activity_users = union_all(
        select(User.id.label("user_id")).where(
            User.created_at >= from_utc,
            User.created_at < to_utc,
        ),
        select(AnalyticsEvent.user_id.label("user_id")).where(
            AnalyticsEvent.user_id.is_not(None),
            AnalyticsEvent.happened_at >= from_utc,
            AnalyticsEvent.happened_at < to_utc,
        ),
        select(QuizSession.user_id.label("user_id")).where(
            QuizSession.started_at >= from_utc,
            QuizSession.started_at < to_utc,
        ),
    ).subquery()
    stmt = select(func.count(distinct(activity_users.c.user_id)))
    return int((await session.execute(stmt)).scalar_one() or 0)


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


async def retention_day_rate(
    session: AsyncSession,
    *,
    from_utc: datetime,
    to_utc: datetime,
    day_offset: int,
) -> float:
    created_rows = (
        await session.execute(
            select(User.id, User.created_at).where(
                User.created_at >= from_utc,
                User.created_at < to_utc,
            )
        )
    ).all()
    if not created_rows:
        return 0.0

    period_end_local = to_utc.astimezone(BERLIN_TZ).date()
    target_by_user: dict[int, date] = {}
    for user_id, created_at in created_rows:
        cohort_day = created_at.astimezone(BERLIN_TZ).date()
        target_day = cohort_day + timedelta(days=day_offset)
        if target_day <= period_end_local:
            target_by_user[int(user_id)] = target_day
    if not target_by_user:
        return 0.0

    eligible_user_ids = tuple(target_by_user.keys())
    target_days = tuple(sorted(set(target_by_user.values())))
    activity_days = build_activity_days_subquery(from_utc=from_utc, to_utc=to_utc)
    event_rows = (
        await session.execute(
            select(activity_days.c.user_id, activity_days.c.local_date_berlin)
            .distinct()
            .where(
                activity_days.c.user_id.in_(eligible_user_ids),
                activity_days.c.local_date_berlin.in_(target_days),
            )
        )
    ).all()

    retained_users: set[int] = set()
    for user_id, local_date in event_rows:
        if user_id is None:
            continue
        normalized_id = int(user_id)
        if target_by_user.get(normalized_id) == local_date:
            retained_users.add(normalized_id)

    base = len(target_by_user)
    if base <= 0:
        return 0.0
    return round((len(retained_users) / base) * 100, 2)


async def count_users_reaching_streak_threshold(
    session: AsyncSession,
    *,
    from_utc: datetime,
    to_utc: datetime,
    threshold: int,
) -> int:
    resolved_threshold = max(1, int(threshold))
    daily_activity = (
        select(
            QuizSession.user_id.label("user_id"),
            QuizSession.local_date_berlin.label("local_date_berlin"),
            func.min(QuizSession.completed_at).label("first_completed_at"),
        )
        .where(
            QuizSession.status == "COMPLETED",
            QuizSession.completed_at.is_not(None),
        )
        .group_by(QuizSession.user_id, QuizSession.local_date_berlin)
        .subquery()
    )
    ordered_days = (
        select(
            daily_activity.c.user_id,
            daily_activity.c.local_date_berlin,
            daily_activity.c.first_completed_at,
            (
                daily_activity.c.local_date_berlin
                - cast(
                    func.row_number().over(
                        partition_by=daily_activity.c.user_id,
                        order_by=daily_activity.c.local_date_berlin,
                    ),
                    Integer,
                )
            ).label("streak_group"),
        )
    ).subquery()
    streak_hits = (
        select(
            ordered_days.c.user_id,
            ordered_days.c.first_completed_at,
            func.row_number()
            .over(
                partition_by=(ordered_days.c.user_id, ordered_days.c.streak_group),
                order_by=ordered_days.c.local_date_berlin,
            )
            .label("streak_rank"),
        )
    ).subquery()
    first_hits_by_user = (
        select(
            streak_hits.c.user_id,
            func.min(streak_hits.c.first_completed_at).label("first_hit_at"),
        )
        .where(streak_hits.c.streak_rank == resolved_threshold)
        .group_by(streak_hits.c.user_id)
        .subquery()
    )
    stmt = select(func.count(first_hits_by_user.c.user_id)).where(
        first_hits_by_user.c.first_hit_at >= from_utc,
        first_hits_by_user.c.first_hit_at < to_utc,
    )
    return int((await session.execute(stmt)).scalar_one() or 0)
