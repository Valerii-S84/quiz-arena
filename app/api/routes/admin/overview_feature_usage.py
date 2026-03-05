from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin.overview_metrics import build_kpi, count_distinct_event_users
from app.api.routes.admin.overview_series import count_referral_referrers


async def _count_event_users(
    session: AsyncSession,
    *,
    event_type: str,
    from_utc: datetime,
    to_utc: datetime,
) -> int:
    return await count_distinct_event_users(
        session,
        event_type=event_type,
        from_utc=from_utc,
        to_utc=to_utc,
    )


def _completion_rate(*, completed: int, created: int) -> float:
    if created <= 0:
        return 0.0
    return (completed / created) * 100


async def build_feature_usage_payload(
    session: AsyncSession,
    *,
    range_start: datetime,
    range_end: datetime,
    prev_start: datetime,
    prev_end: datetime,
) -> dict[str, dict[str, float]]:
    duel_created_now = await _count_event_users(
        session,
        event_type="duel_created",
        from_utc=range_start,
        to_utc=range_end,
    )
    duel_created_prev = await _count_event_users(
        session,
        event_type="duel_created",
        from_utc=prev_start,
        to_utc=prev_end,
    )
    duel_completed_now = await _count_event_users(
        session,
        event_type="duel_completed",
        from_utc=range_start,
        to_utc=range_end,
    )
    duel_completed_prev = await _count_event_users(
        session,
        event_type="duel_completed",
        from_utc=prev_start,
        to_utc=prev_end,
    )
    referral_shared_now = await _count_event_users(
        session,
        event_type="referral_link_shared",
        from_utc=range_start,
        to_utc=range_end,
    )
    referral_shared_prev = await _count_event_users(
        session,
        event_type="referral_link_shared",
        from_utc=prev_start,
        to_utc=prev_end,
    )
    daily_cup_registered_now = await _count_event_users(
        session,
        event_type="daily_cup_registered",
        from_utc=range_start,
        to_utc=range_end,
    )
    daily_cup_registered_prev = await _count_event_users(
        session,
        event_type="daily_cup_registered",
        from_utc=prev_start,
        to_utc=prev_end,
    )
    referral_referrers_now = await count_referral_referrers(
        session,
        from_utc=range_start,
        to_utc=range_end,
    )
    referral_referrers_prev = await count_referral_referrers(
        session,
        from_utc=prev_start,
        to_utc=prev_end,
    )

    duel_completion_now = _completion_rate(completed=duel_completed_now, created=duel_created_now)
    duel_completion_prev = _completion_rate(
        completed=duel_completed_prev,
        created=duel_created_prev,
    )

    return {
        "duel_created_users": build_kpi(
            current=float(duel_created_now),
            previous=float(duel_created_prev),
        ),
        "duel_completed_users": build_kpi(
            current=float(duel_completed_now),
            previous=float(duel_completed_prev),
        ),
        "duel_completion_rate": build_kpi(
            current=duel_completion_now,
            previous=duel_completion_prev,
        ),
        "referral_shared_users": build_kpi(
            current=float(referral_shared_now),
            previous=float(referral_shared_prev),
        ),
        "referral_referrers_started": build_kpi(
            current=float(referral_referrers_now),
            previous=float(referral_referrers_prev),
        ),
        "daily_cup_registered_users": build_kpi(
            current=float(daily_cup_registered_now),
            previous=float(daily_cup_registered_prev),
        ),
    }
