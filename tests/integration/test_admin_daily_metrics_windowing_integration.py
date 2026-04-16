from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.models.daily_metrics import DailyMetrics
from app.db.session import SessionLocal
from app.workers.tasks import admin_daily_metrics
from tests.integration.admin_daily_metrics_test_support import (
    UTC,
    build_entitlement,
    build_purchase,
    build_quiz_session,
    create_user,
    freeze_now,
)
from tests.type_helpers import as_any_dict


@pytest.mark.asyncio
async def test_admin_daily_metrics_clamps_days_back_to_valid_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_now = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    freeze_now(monkeypatch, fixed_now)

    zero_result = as_any_dict(
        await admin_daily_metrics.run_admin_daily_metrics_aggregation_async(days_back=0)
    )
    negative_result = as_any_dict(
        await admin_daily_metrics.run_admin_daily_metrics_aggregation_async(days_back=-3)
    )
    max_result = as_any_dict(
        await admin_daily_metrics.run_admin_daily_metrics_aggregation_async(days_back=99)
    )

    async with SessionLocal.begin() as session:
        rows = list(
            (
                await session.execute(select(DailyMetrics).order_by(DailyMetrics.date.desc()))
            ).scalars()
        )

    assert zero_result["days_processed"] == 1
    assert zero_result["dates"] == ["2026-04-10"]
    assert negative_result["days_processed"] == 1
    assert negative_result["dates"] == ["2026-04-10"]
    assert max_result["days_processed"] == 14
    assert max_result["dates"][0] == "2026-04-10"
    assert max_result["dates"][-1] == "2026-03-28"
    assert len(rows) == 14


@pytest.mark.asyncio
async def test_admin_daily_metrics_respects_berlin_day_boundaries_and_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_now = datetime(2026, 3, 29, 12, 0, tzinfo=UTC)
    local_day = date(2026, 3, 29)
    freeze_now(monkeypatch, fixed_now)
    day_start, day_end = admin_daily_metrics._day_bounds_utc(local_day)

    async with SessionLocal.begin() as session:
        included_user = await create_user(
            session,
            seed="admin-metrics-dst-included-1",
            created_at=day_start,
            last_seen_at=day_start,
        )
        included_user_2 = await create_user(
            session,
            seed="admin-metrics-dst-included-2",
            created_at=day_end - timedelta(minutes=1),
            last_seen_at=day_end - timedelta(seconds=1),
        )
        excluded_old_user = await create_user(
            session,
            seed="admin-metrics-dst-old",
            created_at=day_start - timedelta(days=40),
            last_seen_at=day_start - timedelta(seconds=1),
        )
        excluded_end_user = await create_user(
            session,
            seed="admin-metrics-dst-end",
            created_at=day_end,
            last_seen_at=day_end,
        )

        session.add_all(
            [
                build_purchase(
                    user_id=included_user,
                    stars_amount=50,
                    status="CREDITED",
                    created_at=day_start + timedelta(minutes=5),
                    paid_at=day_start + timedelta(hours=1),
                ),
                build_purchase(
                    user_id=included_user_2,
                    stars_amount=30,
                    status="PAID_UNCREDITED",
                    created_at=day_end - timedelta(hours=1),
                    paid_at=day_end - timedelta(minutes=1),
                ),
                build_purchase(
                    user_id=included_user,
                    stars_amount=99,
                    status="FAILED",
                    created_at=day_start + timedelta(hours=2),
                    paid_at=day_start + timedelta(hours=2),
                ),
                build_purchase(
                    user_id=included_user,
                    stars_amount=77,
                    status="REFUNDED",
                    created_at=day_start + timedelta(hours=3),
                    paid_at=day_start + timedelta(hours=3),
                ),
                build_purchase(
                    user_id=excluded_old_user,
                    stars_amount=88,
                    status="CREDITED",
                    created_at=day_start - timedelta(minutes=10),
                    paid_at=day_start - timedelta(seconds=1),
                ),
            ]
        )
        session.add_all(
            [
                build_quiz_session(
                    user_id=included_user,
                    started_at=day_start + timedelta(minutes=30),
                    local_day=local_day,
                ),
                build_quiz_session(
                    user_id=excluded_end_user,
                    started_at=day_end,
                    local_day=local_day,
                ),
            ]
        )
        session.add_all(
            [
                build_entitlement(
                    user_id=included_user,
                    status="ACTIVE",
                    starts_at=day_start - timedelta(days=1),
                    ends_at=day_end + timedelta(days=5),
                ),
                build_entitlement(
                    user_id=included_user_2,
                    status="EXPIRED",
                    starts_at=day_start - timedelta(days=2),
                    ends_at=day_end + timedelta(days=1),
                ),
                build_entitlement(
                    user_id=excluded_old_user,
                    status="ACTIVE",
                    starts_at=day_end + timedelta(seconds=1),
                    ends_at=day_end + timedelta(days=3),
                ),
                build_entitlement(
                    user_id=excluded_end_user,
                    status="ACTIVE",
                    starts_at=day_start - timedelta(days=3),
                    ends_at=day_end - timedelta(seconds=1),
                ),
            ]
        )

    result = as_any_dict(
        await admin_daily_metrics.run_admin_daily_metrics_aggregation_async(days_back=1)
    )

    async with SessionLocal.begin() as session:
        row = await session.get(DailyMetrics, local_day)

    assert result["days_processed"] == 1
    assert row is not None
    assert row.date == local_day
    assert row.dau == 2
    assert row.wau == 3
    assert row.mau == 3
    assert row.new_users == 2
    assert row.revenue_stars == 80
    assert row.revenue_eur == Decimal("1.60")
    assert row.quizzes_played == 1
    assert row.purchases_count == 2
    assert row.active_subscriptions == 1
