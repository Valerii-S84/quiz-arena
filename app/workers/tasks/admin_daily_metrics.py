from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import distinct, func, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models.daily_metrics import DailyMetrics
from app.db.models.entitlements import Entitlement
from app.db.models.purchases import Purchase
from app.db.models.quiz_sessions import QuizSession
from app.db.models.users import User
from app.db.session import SessionLocal
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)
STAR_TO_EUR_RATE = Decimal("0.02")
BERLIN_TZ = ZoneInfo("Europe/Berlin")


def _clamp_days_back(value: int) -> int:
    return max(1, min(14, int(value)))


def _day_bounds_utc(local_day: date) -> tuple[datetime, datetime]:
    start_local = datetime.combine(local_day, time.min, tzinfo=BERLIN_TZ)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


async def _count_active_users(session, *, from_utc: datetime, to_utc: datetime) -> int:
    stmt = select(func.count(distinct(User.id))).where(
        User.last_seen_at.is_not(None),
        User.last_seen_at >= from_utc,
        User.last_seen_at < to_utc,
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def run_admin_daily_metrics_aggregation_async(*, days_back: int = 2) -> dict[str, object]:
    now_utc = datetime.now(timezone.utc)
    today_berlin = now_utc.astimezone(BERLIN_TZ).date()
    processed: list[str] = []

    async with SessionLocal.begin() as session:
        for offset in range(_clamp_days_back(days_back)):
            target_day = today_berlin - timedelta(days=offset)
            day_start, day_end = _day_bounds_utc(target_day)

            dau = await _count_active_users(session, from_utc=day_start, to_utc=day_end)
            wau = await _count_active_users(
                session, from_utc=day_end - timedelta(days=7), to_utc=day_end
            )
            mau = await _count_active_users(
                session, from_utc=day_end - timedelta(days=30), to_utc=day_end
            )

            new_users = int(
                (
                    await session.execute(
                        select(func.count(User.id)).where(
                            User.created_at >= day_start, User.created_at < day_end
                        )
                    )
                ).scalar_one()
                or 0
            )
            revenue_stars = int(
                (
                    await session.execute(
                        select(func.coalesce(func.sum(Purchase.stars_amount), 0)).where(
                            Purchase.paid_at.is_not(None),
                            Purchase.paid_at >= day_start,
                            Purchase.paid_at < day_end,
                            Purchase.status.in_(("PAID_UNCREDITED", "CREDITED")),
                        )
                    )
                ).scalar_one()
                or 0
            )
            quizzes_played = int(
                (
                    await session.execute(
                        select(func.count(QuizSession.id)).where(
                            QuizSession.started_at >= day_start,
                            QuizSession.started_at < day_end,
                        )
                    )
                ).scalar_one()
                or 0
            )
            purchases_count = int(
                (
                    await session.execute(
                        select(func.count(Purchase.id)).where(
                            Purchase.paid_at.is_not(None),
                            Purchase.paid_at >= day_start,
                            Purchase.paid_at < day_end,
                            Purchase.status.in_(("PAID_UNCREDITED", "CREDITED")),
                        )
                    )
                ).scalar_one()
                or 0
            )
            active_subscriptions = int(
                (
                    await session.execute(
                        select(func.count(Entitlement.id)).where(
                            Entitlement.entitlement_type == "PREMIUM",
                            Entitlement.status == "ACTIVE",
                            Entitlement.starts_at <= day_end,
                            (Entitlement.ends_at.is_(None) | (Entitlement.ends_at >= day_end)),
                        )
                    )
                ).scalar_one()
                or 0
            )

            stmt = insert(DailyMetrics).values(
                date=target_day,
                dau=dau,
                wau=wau,
                mau=mau,
                new_users=new_users,
                revenue_stars=revenue_stars,
                revenue_eur=Decimal(revenue_stars) * STAR_TO_EUR_RATE,
                quizzes_played=quizzes_played,
                purchases_count=purchases_count,
                active_subscriptions=active_subscriptions,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[DailyMetrics.date],
                set_={
                    "dau": stmt.excluded.dau,
                    "wau": stmt.excluded.wau,
                    "mau": stmt.excluded.mau,
                    "new_users": stmt.excluded.new_users,
                    "revenue_stars": stmt.excluded.revenue_stars,
                    "revenue_eur": stmt.excluded.revenue_eur,
                    "quizzes_played": stmt.excluded.quizzes_played,
                    "purchases_count": stmt.excluded.purchases_count,
                    "active_subscriptions": stmt.excluded.active_subscriptions,
                },
            )
            await session.execute(stmt)
            processed.append(target_day.isoformat())

    result = {
        "generated_at": now_utc.isoformat(),
        "days_processed": len(processed),
        "dates": processed,
    }
    logger.info("admin_daily_metrics_aggregation_finished", **result)
    return result


@celery_app.task(name="app.workers.tasks.admin_daily_metrics.run_admin_daily_metrics_aggregation")
def run_admin_daily_metrics_aggregation(days_back: int = 2) -> dict[str, object]:
    return run_async_job(run_admin_daily_metrics_aggregation_async(days_back=days_back))


celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
celery_app.conf.beat_schedule.update(
    {
        "admin-daily-metrics-aggregation-hourly": {
            "task": "app.workers.tasks.admin_daily_metrics.run_admin_daily_metrics_aggregation",
            "schedule": 3600.0,
            "options": {"queue": "q_low"},
        },
    }
)
