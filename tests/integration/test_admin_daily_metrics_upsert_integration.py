from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.db.models.daily_metrics import DailyMetrics
from app.db.models.purchases import Purchase
from app.db.session import SessionLocal
from app.workers.tasks import admin_daily_metrics
from tests.integration.admin_daily_metrics_test_support import (
    UTC,
    build_purchase,
    build_quiz_session,
    create_user,
    freeze_now,
)
from tests.type_helpers import as_any_dict


@pytest.mark.asyncio
async def test_admin_daily_metrics_upserts_existing_rows_and_writes_multiple_days(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_now = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    today = date(2026, 4, 10)
    yesterday = date(2026, 4, 9)
    freeze_now(monkeypatch, fixed_now)
    today_start, _today_end = admin_daily_metrics._day_bounds_utc(today)
    yesterday_start, yesterday_end = admin_daily_metrics._day_bounds_utc(yesterday)

    async with SessionLocal.begin() as session:
        today_user = await create_user(
            session,
            seed="admin-metrics-today",
            created_at=today_start + timedelta(minutes=5),
            last_seen_at=today_start + timedelta(hours=1),
        )
        yesterday_user = await create_user(
            session,
            seed="admin-metrics-yesterday",
            created_at=yesterday_start + timedelta(minutes=5),
            last_seen_at=yesterday_start + timedelta(hours=1),
        )
        session.add_all(
            [
                build_purchase(
                    user_id=today_user,
                    stars_amount=40,
                    status="CREDITED",
                    created_at=today_start + timedelta(minutes=10),
                    paid_at=today_start + timedelta(minutes=11),
                ),
                build_purchase(
                    user_id=yesterday_user,
                    stars_amount=25,
                    status="PAID_UNCREDITED",
                    created_at=yesterday_start + timedelta(minutes=10),
                    paid_at=yesterday_start + timedelta(minutes=11),
                ),
            ]
        )
        session.add(
            build_quiz_session(
                user_id=yesterday_user,
                started_at=yesterday_end - timedelta(minutes=30),
                local_day=yesterday,
            )
        )

    first_result = as_any_dict(
        await admin_daily_metrics.run_admin_daily_metrics_aggregation_async(days_back=2)
    )

    async with SessionLocal.begin() as session:
        initial_rows = list(
            (
                await session.execute(select(DailyMetrics).order_by(DailyMetrics.date.asc()))
            ).scalars()
        )

    assert first_result["days_processed"] == 2
    assert [row.date for row in initial_rows] == [yesterday, today]
    assert initial_rows[0].revenue_stars == 25
    assert initial_rows[0].purchases_count == 1
    assert initial_rows[0].quizzes_played == 1
    assert initial_rows[1].revenue_stars == 40
    assert initial_rows[1].purchases_count == 1

    async with SessionLocal.begin() as session:
        today_user = int(
            (
                await session.execute(
                    select(func.min(Purchase.user_id)).where(
                        Purchase.paid_at >= today_start,
                        Purchase.paid_at < today_start + timedelta(days=1),
                    )
                )
            ).scalar_one()
        )
        session.add(
            build_purchase(
                user_id=today_user,
                stars_amount=10,
                status="CREDITED",
                created_at=today_start + timedelta(hours=2),
                paid_at=today_start + timedelta(hours=2, minutes=1),
            )
        )

    second_result = as_any_dict(
        await admin_daily_metrics.run_admin_daily_metrics_aggregation_async(days_back=2)
    )

    async with SessionLocal.begin() as session:
        updated_rows = list(
            (
                await session.execute(select(DailyMetrics).order_by(DailyMetrics.date.asc()))
            ).scalars()
        )

    assert second_result["days_processed"] == 2
    assert len(updated_rows) == 2
    assert updated_rows[0].date == yesterday
    assert updated_rows[0].revenue_stars == 25
    assert updated_rows[0].purchases_count == 1
    assert updated_rows[1].date == today
    assert updated_rows[1].revenue_stars == 50
    assert updated_rows[1].purchases_count == 2
