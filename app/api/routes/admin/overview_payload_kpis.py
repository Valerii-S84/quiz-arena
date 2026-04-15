from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin.overview_activity_metrics import count_distinct_users, retention_day_rate
from app.api.routes.admin.overview_metrics import STAR_TO_EUR_RATE, build_kpi, sum_revenue_stars
from app.api.routes.admin.overview_series import count_new_users
from app.db.models.entitlements import Entitlement


@dataclass(frozen=True, slots=True)
class OverviewWindows:
    current_start: datetime
    current_end: datetime
    previous_start: datetime
    previous_end: datetime


@dataclass(frozen=True, slots=True)
class RangeKpiSnapshot:
    kpis: dict[str, dict[str, float]]
    new_users_now: int
    new_users_prev: int


def build_windows(*, now_utc: datetime, days: int) -> OverviewWindows:
    current_end = now_utc
    current_start = now_utc - timedelta(days=days)
    previous_end = current_start
    previous_start = current_start - timedelta(days=days)
    return OverviewWindows(
        current_start=current_start,
        current_end=current_end,
        previous_start=previous_start,
        previous_end=previous_end,
    )


async def _count_active_subscriptions(session: AsyncSession, *, at_utc: datetime) -> int:
    stmt = select(func.count(Entitlement.id)).where(
        Entitlement.entitlement_type == "PREMIUM",
        Entitlement.status == "ACTIVE",
        Entitlement.starts_at <= at_utc,
        (Entitlement.ends_at.is_(None) | (Entitlement.ends_at >= at_utc)),
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def build_activity_kpis(
    session: AsyncSession,
    *,
    now_utc: datetime,
    windows: OverviewWindows,
) -> dict[str, dict[str, float]]:
    dau_now = await count_distinct_users(
        session, from_utc=now_utc - timedelta(days=1), to_utc=now_utc
    )
    dau_prev = await count_distinct_users(
        session,
        from_utc=windows.previous_end - timedelta(days=1),
        to_utc=windows.previous_end,
    )
    wau_now = await count_distinct_users(
        session, from_utc=now_utc - timedelta(days=7), to_utc=now_utc
    )
    wau_prev = await count_distinct_users(
        session,
        from_utc=windows.previous_end - timedelta(days=7),
        to_utc=windows.previous_end,
    )
    mau_now = await count_distinct_users(
        session, from_utc=now_utc - timedelta(days=30), to_utc=now_utc
    )
    mau_prev = await count_distinct_users(
        session,
        from_utc=windows.previous_end - timedelta(days=30),
        to_utc=windows.previous_end,
    )
    return {
        "dau": build_kpi(current=float(dau_now), previous=float(dau_prev)),
        "wau": build_kpi(current=float(wau_now), previous=float(wau_prev)),
        "mau": build_kpi(current=float(mau_now), previous=float(mau_prev)),
    }


async def build_range_kpis(
    session: AsyncSession,
    *,
    windows: OverviewWindows,
) -> RangeKpiSnapshot:
    new_users_now = await count_new_users(
        session, from_utc=windows.current_start, to_utc=windows.current_end
    )
    new_users_prev = await count_new_users(
        session, from_utc=windows.previous_start, to_utc=windows.previous_end
    )
    retention_d1_now = await retention_day_rate(
        session,
        from_utc=windows.current_start,
        to_utc=windows.current_end,
        day_offset=1,
    )
    retention_d1_prev = await retention_day_rate(
        session,
        from_utc=windows.previous_start,
        to_utc=windows.previous_end,
        day_offset=1,
    )
    retention_d7_now = await retention_day_rate(
        session,
        from_utc=windows.current_start,
        to_utc=windows.current_end,
        day_offset=7,
    )
    retention_d7_prev = await retention_day_rate(
        session,
        from_utc=windows.previous_start,
        to_utc=windows.previous_end,
        day_offset=7,
    )
    revenue_stars_now = await sum_revenue_stars(
        session, from_utc=windows.current_start, to_utc=windows.current_end
    )
    revenue_stars_prev = await sum_revenue_stars(
        session, from_utc=windows.previous_start, to_utc=windows.previous_end
    )
    return RangeKpiSnapshot(
        kpis={
            "new_users": build_kpi(current=float(new_users_now), previous=float(new_users_prev)),
            "retention_d1": build_kpi(current=retention_d1_now, previous=retention_d1_prev),
            "retention_d7": build_kpi(current=retention_d7_now, previous=retention_d7_prev),
            "revenue_stars": build_kpi(
                current=float(revenue_stars_now),
                previous=float(revenue_stars_prev),
            ),
            "revenue_eur": build_kpi(
                current=float(Decimal(revenue_stars_now) * STAR_TO_EUR_RATE),
                previous=float(Decimal(revenue_stars_prev) * STAR_TO_EUR_RATE),
            ),
        },
        new_users_now=new_users_now,
        new_users_prev=new_users_prev,
    )
async def build_subscription_kpis(
    session: AsyncSession,
    *,
    now_utc: datetime,
    previous_end: datetime,
) -> dict[str, dict[str, float]]:
    active_subs_now = await _count_active_subscriptions(session, at_utc=now_utc)
    active_subs_prev = await _count_active_subscriptions(session, at_utc=previous_end)
    return {
        "active_subscriptions": build_kpi(
            current=float(active_subs_now),
            previous=float(active_subs_prev),
        )
    }
__all__ = [
    "OverviewWindows",
    "RangeKpiSnapshot",
    "build_activity_kpis",
    "build_range_kpis",
    "build_subscription_kpis",
    "build_windows",
]
