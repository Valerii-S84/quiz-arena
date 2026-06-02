from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin.overview_feature_usage import build_feature_usage_payload
from app.api.routes.admin.overview_language import fetch_user_language_distribution
from app.api.routes.admin.overview_payload_conversion import (
    build_conversion_kpis,
    load_conversion_snapshot,
)
from app.api.routes.admin.overview_payload_kpis import (
    build_activity_kpis,
    build_range_kpis,
    build_subscription_kpis,
    build_windows,
)
from app.api.routes.admin.overview_series import (
    fetch_alert_inputs,
    fetch_hourly_activity_series,
    fetch_revenue_series,
    fetch_top_products,
    fetch_users_series,
)
from app.api.routes.admin.overview_streak_metrics import count_users_reaching_streak_threshold


def _build_funnel(
    *,
    first_quiz_users_now: int,
    first_purchase_users_now: int,
    start_users_now: int,
    streak3_users: int,
) -> list[dict[str, object]]:
    return [
        {"step": "Start", "value": start_users_now},
        {"step": "First Quiz", "value": first_quiz_users_now},
        {"step": "Streak 3+", "value": streak3_users},
        {"step": "Purchase", "value": first_purchase_users_now},
    ]


async def _build_alerts(
    session: AsyncSession,
    *,
    now_utc: datetime,
    quiz_to_purchase_now: float,
    quiz_to_purchase_prev: float,
) -> list[dict[str, object]]:
    webhook_errors, invalid_attempts = await fetch_alert_inputs(session, now_utc=now_utc)

    alerts: list[dict[str, object]] = []
    if webhook_errors > 0:
        alerts.append({"type": "webhook_errors", "severity": "high", "count": webhook_errors})
    if quiz_to_purchase_prev > 0 and quiz_to_purchase_now < quiz_to_purchase_prev * 0.8:
        alerts.append(
            {
                "type": "conversion_drop",
                "severity": "medium",
                "from": round(quiz_to_purchase_prev, 2),
                "to": round(quiz_to_purchase_now, 2),
            }
        )
    if invalid_attempts >= 25:
        alerts.append(
            {
                "type": "suspicious_activity",
                "severity": "medium",
                "invalid_promo_attempts_1h": invalid_attempts,
            }
        )
    return alerts


async def build_overview_payload(
    session: AsyncSession,
    *,
    now_utc: datetime,
    days: int,
) -> dict[str, object]:
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
    revenue_series = await fetch_revenue_series(
        session, from_utc=windows.current_start, to_utc=windows.current_end
    )
    users_series = await fetch_users_series(
        session, from_utc=windows.current_start, to_utc=windows.current_end
    )
    hourly_activity_series = await fetch_hourly_activity_series(
        session,
        from_utc=windows.current_start,
        to_utc=windows.current_end,
    )
    top_products = await fetch_top_products(
        session, from_utc=windows.current_start, to_utc=windows.current_end
    )
    user_language_distribution = await fetch_user_language_distribution(session)
    feature_usage = await build_feature_usage_payload(
        session,
        range_start=windows.current_start,
        range_end=windows.current_end,
        prev_start=windows.previous_start,
        prev_end=windows.previous_end,
    )
    alerts = await _build_alerts(
        session,
        now_utc=now_utc,
        quiz_to_purchase_now=conversion_snapshot.quiz_to_purchase_now,
        quiz_to_purchase_prev=conversion_snapshot.quiz_to_purchase_prev,
    )
    return {
        "period": f"{days}d",
        "generated_at": now_utc,
        "kpis": {
            **activity_kpis,
            **range_snapshot.kpis,
            **subscription_kpis,
            **build_conversion_kpis(conversion_snapshot),
        },
        "revenue_series": revenue_series,
        "users_series": users_series,
        "hourly_activity_series": hourly_activity_series,
        "funnel": _build_funnel(
            first_quiz_users_now=conversion_snapshot.first_quiz_users_now,
            first_purchase_users_now=conversion_snapshot.first_purchase_users_now,
            start_users_now=conversion_snapshot.start_users_now,
            streak3_users=streak3_users,
        ),
        "top_products": top_products,
        "user_language_distribution": user_language_distribution,
        "user_age_distribution": [],
        "user_gender_distribution": [],
        "feature_usage": feature_usage,
        "alerts": alerts,
    }


__all__ = ["build_overview_payload"]
