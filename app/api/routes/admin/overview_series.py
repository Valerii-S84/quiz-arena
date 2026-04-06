from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import distinct, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.api.routes.admin.overview_activity_metrics import build_activity_days_subquery
from app.api.routes.admin.overview_metrics import STAR_TO_EUR_RATE
from app.db.models.outbox_events import OutboxEvent
from app.db.models.promo_attempts import PromoAttempt
from app.db.models.purchases import Purchase
from app.db.models.quiz_sessions import QuizSession
from app.db.models.referrals import Referral
from app.db.models.users import User

BERLIN_TIMEZONE_SQL: ColumnElement[str] = literal_column("'Europe/Berlin'")


async def count_new_users(session: AsyncSession, *, from_utc: datetime, to_utc: datetime) -> int:
    stmt = select(func.count(User.id)).where(User.created_at >= from_utc, User.created_at < to_utc)
    return int((await session.execute(stmt)).scalar_one() or 0)


async def count_quiz_users(session: AsyncSession, *, from_utc: datetime, to_utc: datetime) -> int:
    stmt = select(func.count(distinct(QuizSession.user_id))).where(
        QuizSession.started_at >= from_utc,
        QuizSession.started_at < to_utc,
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def count_first_quiz_users(
    session: AsyncSession, *, from_utc: datetime, to_utc: datetime
) -> int:
    first_quiz_by_user = (
        select(
            QuizSession.user_id.label("user_id"),
            func.min(QuizSession.started_at).label("first_started_at"),
        )
        .where(QuizSession.status != "CANCELED")
        .group_by(QuizSession.user_id)
        .subquery()
    )
    stmt = select(func.count(first_quiz_by_user.c.user_id)).where(
        first_quiz_by_user.c.first_started_at >= from_utc,
        first_quiz_by_user.c.first_started_at < to_utc,
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def count_referral_referrers(
    session: AsyncSession,
    *,
    from_utc: datetime,
    to_utc: datetime,
) -> int:
    stmt = select(func.count(distinct(Referral.referrer_user_id))).where(
        Referral.created_at >= from_utc,
        Referral.created_at < to_utc,
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def fetch_revenue_series(
    session: AsyncSession,
    *,
    from_utc: datetime,
    to_utc: datetime,
) -> list[dict[str, object]]:
    rows = (
        await session.execute(
            select(func.date(Purchase.paid_at), func.coalesce(func.sum(Purchase.stars_amount), 0))
            .where(Purchase.paid_at >= from_utc, Purchase.paid_at < to_utc)
            .group_by(func.date(Purchase.paid_at))
            .order_by(func.date(Purchase.paid_at))
        )
    ).all()
    return [
        {
            "date": row_day.isoformat(),
            "stars": int(stars),
            "eur": float(Decimal(stars) * STAR_TO_EUR_RATE),
        }
        for row_day, stars in rows
        if isinstance(row_day, date)
    ]


async def fetch_users_series(
    session: AsyncSession,
    *,
    from_utc: datetime,
    to_utc: datetime,
) -> list[dict[str, object]]:
    created_day_berlin = func.date(func.timezone(BERLIN_TIMEZONE_SQL, User.created_at))
    new_by_day = {
        row_day.isoformat(): int(total)
        for row_day, total in (
            await session.execute(
                select(
                    created_day_berlin,
                    func.count(User.id),
                )
                .where(User.created_at >= from_utc, User.created_at < to_utc)
                .group_by(created_day_berlin)
            )
        ).all()
    }
    activity_days = build_activity_days_subquery(from_utc=from_utc, to_utc=to_utc)
    active_by_day = {
        row_day.isoformat(): int(total)
        for row_day, total in (
            await session.execute(
                select(
                    activity_days.c.local_date_berlin,
                    func.count(distinct(activity_days.c.user_id)),
                ).group_by(activity_days.c.local_date_berlin)
            )
        ).all()
    }
    return [
        {
            "date": key,
            "new_users": new_by_day.get(key, 0),
            "active_users": active_by_day.get(key, 0),
        }
        for key in sorted(set(new_by_day) | set(active_by_day))
    ]


async def fetch_top_products(
    session: AsyncSession,
    *,
    from_utc: datetime,
    to_utc: datetime,
) -> list[dict[str, object]]:
    rows = (
        await session.execute(
            select(Purchase.product_code, func.coalesce(func.sum(Purchase.stars_amount), 0))
            .where(Purchase.paid_at >= from_utc, Purchase.paid_at < to_utc)
            .group_by(Purchase.product_code)
            .order_by(func.coalesce(func.sum(Purchase.stars_amount), 0).desc())
            .limit(5)
        )
    ).all()
    return [{"product": code, "revenue_stars": int(total)} for code, total in rows]


async def fetch_alert_inputs(session: AsyncSession, *, now_utc: datetime) -> tuple[int, int]:
    webhook_errors = int(
        (
            await session.execute(
                select(func.count(OutboxEvent.id)).where(
                    OutboxEvent.created_at >= now_utc - timedelta(hours=24),
                    OutboxEvent.status.in_(("FAILED", "ERROR")),
                )
            )
        ).scalar_one()
        or 0
    )
    invalid_attempts = int(
        (
            await session.execute(
                select(func.count(PromoAttempt.id)).where(
                    PromoAttempt.attempted_at >= now_utc - timedelta(hours=1),
                    PromoAttempt.result == "INVALID",
                )
            )
        ).scalar_one()
        or 0
    )
    return webhook_errors, invalid_attempts
