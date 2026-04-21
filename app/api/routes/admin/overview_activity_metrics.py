from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Integer, cast, distinct, func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analytics_events import AnalyticsEvent
from app.db.models.quiz_sessions import QuizSession
from app.db.models.users import User

BERLIN_TZ = ZoneInfo("Europe/Berlin")


def build_activity_days_subquery(*, from_utc: datetime, to_utc: datetime):
    return union_all(
        select(
            User.id.label("user_id"),
            func.date(func.timezone("Europe/Berlin", User.created_at)).label("local_date_berlin"),
        ).where(User.created_at >= from_utc, User.created_at < to_utc),
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


def build_activity_day_hours_subquery(*, from_utc: datetime, to_utc: datetime):
    return union_all(
        select(
            User.id.label("user_id"),
            func.date(func.timezone("Europe/Berlin", User.created_at)).label("local_date_berlin"),
            cast(
                func.extract("hour", func.timezone("Europe/Berlin", User.created_at)),
                Integer,
            ).label("local_hour_berlin"),
        ).where(User.created_at >= from_utc, User.created_at < to_utc),
        select(
            AnalyticsEvent.user_id.label("user_id"),
            AnalyticsEvent.local_date_berlin.label("local_date_berlin"),
            cast(
                func.extract("hour", func.timezone("Europe/Berlin", AnalyticsEvent.happened_at)),
                Integer,
            ).label("local_hour_berlin"),
        ).where(
            AnalyticsEvent.user_id.is_not(None),
            AnalyticsEvent.happened_at >= from_utc,
            AnalyticsEvent.happened_at < to_utc,
        ),
        select(
            QuizSession.user_id.label("user_id"),
            QuizSession.local_date_berlin.label("local_date_berlin"),
            cast(
                func.extract("hour", func.timezone("Europe/Berlin", QuizSession.started_at)),
                Integer,
            ).label("local_hour_berlin"),
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
            User.created_at >= from_utc, User.created_at < to_utc
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
                User.created_at >= from_utc, User.created_at < to_utc
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

    activity_days = build_activity_days_subquery(from_utc=from_utc, to_utc=to_utc)
    target_days = tuple(sorted(set(target_by_user.values())))
    event_rows = (
        await session.execute(
            select(activity_days.c.user_id, activity_days.c.local_date_berlin)
            .distinct()
            .where(
                activity_days.c.user_id.in_(tuple(target_by_user)),
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
