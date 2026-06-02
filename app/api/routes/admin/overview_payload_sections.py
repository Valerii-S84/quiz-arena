from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin.overview_feature_usage import build_feature_usage_payload
from app.api.routes.admin.overview_language import fetch_user_language_distribution
from app.api.routes.admin.overview_payload_conversion import (
    ConversionSnapshot,
    build_conversion_kpis,
    load_conversion_snapshot,
)
from app.api.routes.admin.overview_payload_kpis import (
    OverviewWindows,
    build_activity_kpis,
    build_range_kpis,
    build_subscription_kpis,
    build_windows,
)
from app.api.routes.admin.overview_series import (
    fetch_hourly_activity_series,
    fetch_revenue_series,
    fetch_top_products,
    fetch_users_series,
)
from app.api.routes.admin.overview_streak_metrics import count_users_reaching_streak_threshold


@dataclass(frozen=True, slots=True)
class OverviewCoreSnapshot:
    windows: OverviewWindows
    activity_kpis: dict[str, dict[str, float]]
    range_kpis: dict[str, dict[str, float]]
    conversion_snapshot: ConversionSnapshot
    subscription_kpis: dict[str, dict[str, float]]
    streak3_users: int


async def load_core_snapshot(
    session: AsyncSession,
    *,
    now_utc: datetime,
    days: int,
) -> OverviewCoreSnapshot:
    windows = build_windows(now_utc=now_utc, days=days)
    activity_kpis = await build_activity_kpis(session, now_utc=now_utc, windows=windows)
    range_snapshot = await build_range_kpis(session, windows=windows)
    conversion_snapshot = await load_conversion_snapshot(
        session,
        start_users_now=range_snapshot.new_users_now,
        start_users_prev=range_snapshot.new_users_prev,
        windows=windows,
    )
    subscription_kpis = await build_subscription_kpis(
        session,
        now_utc=now_utc,
        previous_end=windows.previous_end,
    )
    streak3_users = await count_users_reaching_streak_threshold(
        session,
        from_utc=windows.current_start,
        to_utc=windows.current_end,
        threshold=3,
    )
    return OverviewCoreSnapshot(
        windows=windows,
        activity_kpis=activity_kpis,
        range_kpis=range_snapshot.kpis,
        conversion_snapshot=conversion_snapshot,
        subscription_kpis=subscription_kpis,
        streak3_users=streak3_users,
    )


async def load_dashboard_sections(
    session: AsyncSession,
    *,
    windows: OverviewWindows,
) -> dict[str, object]:
    return {
        "revenue_series": await fetch_revenue_series(
            session,
            from_utc=windows.current_start,
            to_utc=windows.current_end,
        ),
        "users_series": await fetch_users_series(
            session,
            from_utc=windows.current_start,
            to_utc=windows.current_end,
        ),
        "hourly_activity_series": await fetch_hourly_activity_series(
            session,
            from_utc=windows.current_start,
            to_utc=windows.current_end,
        ),
        "top_products": await fetch_top_products(
            session,
            from_utc=windows.current_start,
            to_utc=windows.current_end,
        ),
        "user_language_distribution": await fetch_user_language_distribution(session),
        "user_age_distribution": [],
        "user_gender_distribution": [],
        "feature_usage": await build_feature_usage_payload(
            session,
            range_start=windows.current_start,
            range_end=windows.current_end,
            prev_start=windows.previous_start,
            prev_end=windows.previous_end,
        ),
    }


def build_overview_kpis(core: OverviewCoreSnapshot) -> dict[str, dict[str, float]]:
    return {
        **core.activity_kpis,
        **core.range_kpis,
        **core.subscription_kpis,
        **build_conversion_kpis(core.conversion_snapshot),
    }


def build_overview_funnel(core: OverviewCoreSnapshot) -> list[dict[str, object]]:
    snapshot = core.conversion_snapshot
    return [
        {"step": "Start", "value": snapshot.start_users_now},
        {"step": "First Quiz", "value": snapshot.first_quiz_users_now},
        {"step": "Streak 3+", "value": core.streak3_users},
        {"step": "Purchase", "value": snapshot.first_purchase_users_now},
    ]
