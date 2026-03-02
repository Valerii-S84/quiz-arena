from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin.overview_metrics import (
    STAR_TO_EUR_RATE,
    build_kpi,
    count_distinct_event_users,
    count_distinct_users,
    count_purchase_users,
    retention_day_rate,
    sum_revenue_stars,
)
from app.api.routes.admin.overview_series import (
    count_new_users,
    count_quiz_users,
    fetch_alert_inputs,
    fetch_revenue_series,
    fetch_top_products,
    fetch_users_series,
)
from app.db.models.entitlements import Entitlement
from app.db.models.streak_state import StreakState


async def _count_active_subscriptions(session: AsyncSession, *, at_utc: datetime) -> int:
    stmt = select(func.count(Entitlement.id)).where(
        Entitlement.entitlement_type == "PREMIUM",
        Entitlement.status == "ACTIVE",
        Entitlement.starts_at <= at_utc,
        (Entitlement.ends_at.is_(None) | (Entitlement.ends_at >= at_utc)),
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def _count_streak_3_plus_users(session: AsyncSession) -> int:
    stmt = select(func.count(StreakState.user_id)).where(StreakState.current_streak >= 3)
    return int((await session.execute(stmt)).scalar_one() or 0)


async def build_overview_payload(
    session: AsyncSession,
    *,
    now_utc: datetime,
    days: int,
) -> dict[str, object]:
    range_end = now_utc
    range_start = now_utc - timedelta(days=days)
    prev_end = range_start
    prev_start = range_start - timedelta(days=days)

    dau_now = await count_distinct_users(
        session, from_utc=now_utc - timedelta(days=1), to_utc=now_utc
    )
    dau_prev = await count_distinct_users(
        session,
        from_utc=prev_end - timedelta(days=1),
        to_utc=prev_end,
    )
    wau_now = await count_distinct_users(
        session, from_utc=now_utc - timedelta(days=7), to_utc=now_utc
    )
    wau_prev = await count_distinct_users(
        session, from_utc=prev_end - timedelta(days=7), to_utc=prev_end
    )
    mau_now = await count_distinct_users(
        session, from_utc=now_utc - timedelta(days=30), to_utc=now_utc
    )
    mau_prev = await count_distinct_users(
        session, from_utc=prev_end - timedelta(days=30), to_utc=prev_end
    )

    new_users_now = await count_new_users(session, from_utc=range_start, to_utc=range_end)
    new_users_prev = await count_new_users(session, from_utc=prev_start, to_utc=prev_end)

    retention_d1_now = await retention_day_rate(
        session,
        from_utc=range_start,
        to_utc=range_end,
        day_offset=1,
    )
    retention_d1_prev = await retention_day_rate(
        session,
        from_utc=prev_start,
        to_utc=prev_end,
        day_offset=1,
    )
    retention_d7_now = await retention_day_rate(
        session,
        from_utc=range_start,
        to_utc=range_end,
        day_offset=7,
    )
    retention_d7_prev = await retention_day_rate(
        session,
        from_utc=prev_start,
        to_utc=prev_end,
        day_offset=7,
    )

    revenue_stars_now = await sum_revenue_stars(session, from_utc=range_start, to_utc=range_end)
    revenue_stars_prev = await sum_revenue_stars(session, from_utc=prev_start, to_utc=prev_end)

    start_users_now = await count_distinct_event_users(
        session,
        event_type="bot_start_pressed",
        from_utc=range_start,
        to_utc=range_end,
    )
    start_users_prev = await count_distinct_event_users(
        session,
        event_type="bot_start_pressed",
        from_utc=prev_start,
        to_utc=prev_end,
    )
    quiz_users_now = await count_quiz_users(session, from_utc=range_start, to_utc=range_end)
    quiz_users_prev = await count_quiz_users(session, from_utc=prev_start, to_utc=prev_end)
    purchase_users_now = await count_purchase_users(session, from_utc=range_start, to_utc=range_end)
    purchase_users_prev = await count_purchase_users(session, from_utc=prev_start, to_utc=prev_end)

    start_to_quiz_now = (quiz_users_now / start_users_now * 100) if start_users_now > 0 else 0.0
    start_to_quiz_prev = (quiz_users_prev / start_users_prev * 100) if start_users_prev > 0 else 0.0
    quiz_to_purchase_now = (
        (purchase_users_now / quiz_users_now * 100) if quiz_users_now > 0 else 0.0
    )
    quiz_to_purchase_prev = (
        (purchase_users_prev / quiz_users_prev * 100) if quiz_users_prev > 0 else 0.0
    )

    active_subs_now = await _count_active_subscriptions(session, at_utc=now_utc)
    active_subs_prev = await _count_active_subscriptions(session, at_utc=prev_end)
    streak3_users = await _count_streak_3_plus_users(session)

    revenue_series = await fetch_revenue_series(session, from_utc=range_start, to_utc=range_end)
    users_series = await fetch_users_series(session, from_utc=range_start, to_utc=range_end)
    top_products = await fetch_top_products(session, from_utc=range_start, to_utc=range_end)

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

    return {
        "period": f"{days}d",
        "generated_at": now_utc,
        "kpis": {
            "dau": build_kpi(current=float(dau_now), previous=float(dau_prev)),
            "wau": build_kpi(current=float(wau_now), previous=float(wau_prev)),
            "mau": build_kpi(current=float(mau_now), previous=float(mau_prev)),
            "new_users": build_kpi(current=float(new_users_now), previous=float(new_users_prev)),
            "retention_d1": build_kpi(current=retention_d1_now, previous=retention_d1_prev),
            "retention_d7": build_kpi(current=retention_d7_now, previous=retention_d7_prev),
            "revenue_stars": build_kpi(
                current=float(revenue_stars_now), previous=float(revenue_stars_prev)
            ),
            "revenue_eur": build_kpi(
                current=float(Decimal(revenue_stars_now) * STAR_TO_EUR_RATE),
                previous=float(Decimal(revenue_stars_prev) * STAR_TO_EUR_RATE),
            ),
            "active_subscriptions": build_kpi(
                current=float(active_subs_now), previous=float(active_subs_prev)
            ),
            "start_users": build_kpi(
                current=float(start_users_now), previous=float(start_users_prev)
            ),
            "conversion_start_to_quiz": build_kpi(
                current=start_to_quiz_now, previous=start_to_quiz_prev
            ),
            "conversion_quiz_to_purchase": build_kpi(
                current=quiz_to_purchase_now, previous=quiz_to_purchase_prev
            ),
        },
        "revenue_series": revenue_series,
        "users_series": users_series,
        "funnel": [
            {"step": "Start", "value": start_users_now},
            {"step": "First Quiz", "value": quiz_users_now},
            {"step": "Streak 3+", "value": streak3_users},
            {"step": "Purchase", "value": purchase_users_now},
        ],
        "top_products": top_products,
        "alerts": alerts,
    }
