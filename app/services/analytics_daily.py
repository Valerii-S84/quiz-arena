from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.analytics_repo import AnalyticsDailyUpsert, AnalyticsRepo
from app.economy.energy.constants import BERLIN_TIMEZONE

ENERGY_ZERO_EVENT = "gameplay_energy_zero"
STREAK_LOST_EVENT = "streak_lost"
REFERRAL_REWARD_MILESTONE_EVENT = "referral_reward_milestone_available"
REFERRAL_REWARD_GRANTED_EVENT = "referral_reward_granted"
PURCHASE_INIT_EVENT = "purchase_init_created"
PURCHASE_INVOICE_SENT_EVENT = "purchase_invoice_sent"
PURCHASE_PRECHECKOUT_OK_EVENT = "purchase_precheckout_ok"
PURCHASE_PAID_UNCREDITED_EVENT = "purchase_paid_uncredited"
PURCHASE_CREDITED_EVENT = "purchase_credited"


@dataclass(frozen=True, slots=True)
class AnalyticsDailySnapshot:
    row: AnalyticsDailyUpsert
    day_start_utc: datetime
    day_end_utc: datetime


def _safe_rate(*, numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _berlin_day_bounds_utc(local_date_berlin: date) -> tuple[datetime, datetime]:
    tz = ZoneInfo(BERLIN_TIMEZONE)
    day_start_local = datetime.combine(local_date_berlin, time.min, tzinfo=tz)
    day_end_local = day_start_local + timedelta(days=1)
    return (
        day_start_local.astimezone(ZoneInfo("UTC")),
        day_end_local.astimezone(ZoneInfo("UTC")),
    )


async def build_daily_snapshot(
    session: AsyncSession,
    *,
    local_date_berlin: date,
    now_utc: datetime,
) -> AnalyticsDailySnapshot:
    day_start_utc, day_end_utc = _berlin_day_bounds_utc(local_date_berlin)
    wau_start_utc = day_end_utc - timedelta(days=7)
    mau_start_utc = day_end_utc - timedelta(days=30)

    dau = await AnalyticsRepo.count_distinct_active_users_between(
        session,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
    )
    wau = await AnalyticsRepo.count_distinct_active_users_between(
        session,
        from_utc=wau_start_utc,
        to_utc=day_end_utc,
    )
    mau = await AnalyticsRepo.count_distinct_active_users_between(
        session,
        from_utc=mau_start_utc,
        to_utc=day_end_utc,
    )

    purchases_credited_total = await AnalyticsRepo.count_credited_purchases_between(
        session,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
    )
    purchasers_total = await AnalyticsRepo.count_distinct_credited_purchasers_between(
        session,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
    )
    promo_to_paid_conversions_total = await AnalyticsRepo.count_promo_to_paid_conversions_between(
        session,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
    )

    promo_redemptions_total = await AnalyticsRepo.count_promo_redemptions_between(
        session,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
    )
    promo_redemptions_applied_total = await AnalyticsRepo.count_applied_promo_redemptions_between(
        session,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
    )

    quiz_sessions_started_total = await AnalyticsRepo.count_quiz_sessions_started_between(
        session,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
    )
    quiz_sessions_completed_total = await AnalyticsRepo.count_quiz_sessions_completed_between(
        session,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
    )

    event_counts = await AnalyticsRepo.count_events_by_type_between(
        session,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
        event_types=(
            ENERGY_ZERO_EVENT,
            STREAK_LOST_EVENT,
            REFERRAL_REWARD_MILESTONE_EVENT,
            REFERRAL_REWARD_GRANTED_EVENT,
            PURCHASE_INIT_EVENT,
            PURCHASE_INVOICE_SENT_EVENT,
            PURCHASE_PRECHECKOUT_OK_EVENT,
            PURCHASE_PAID_UNCREDITED_EVENT,
            PURCHASE_CREDITED_EVENT,
        ),
    )

    return AnalyticsDailySnapshot(
        row=AnalyticsDailyUpsert(
            local_date_berlin=local_date_berlin,
            dau=dau,
            wau=wau,
            mau=mau,
            purchases_credited_total=purchases_credited_total,
            purchasers_total=purchasers_total,
            purchase_rate=_safe_rate(numerator=purchasers_total, denominator=dau),
            promo_redemptions_total=promo_redemptions_total,
            promo_redemptions_applied_total=promo_redemptions_applied_total,
            promo_redemption_rate=_safe_rate(
                numerator=promo_redemptions_applied_total,
                denominator=promo_redemptions_total,
            ),
            promo_to_paid_conversions_total=promo_to_paid_conversions_total,
            quiz_sessions_started_total=quiz_sessions_started_total,
            quiz_sessions_completed_total=quiz_sessions_completed_total,
            gameplay_completion_rate=_safe_rate(
                numerator=quiz_sessions_completed_total,
                denominator=quiz_sessions_started_total,
            ),
            energy_zero_events_total=event_counts.get(ENERGY_ZERO_EVENT, 0),
            streak_lost_events_total=event_counts.get(STREAK_LOST_EVENT, 0),
            referral_reward_milestone_events_total=event_counts.get(
                REFERRAL_REWARD_MILESTONE_EVENT, 0
            ),
            referral_reward_granted_events_total=event_counts.get(REFERRAL_REWARD_GRANTED_EVENT, 0),
            purchase_init_events_total=event_counts.get(PURCHASE_INIT_EVENT, 0),
            purchase_invoice_sent_events_total=event_counts.get(PURCHASE_INVOICE_SENT_EVENT, 0),
            purchase_precheckout_ok_events_total=event_counts.get(PURCHASE_PRECHECKOUT_OK_EVENT, 0),
            purchase_paid_uncredited_events_total=event_counts.get(
                PURCHASE_PAID_UNCREDITED_EVENT, 0
            ),
            purchase_credited_events_total=event_counts.get(PURCHASE_CREDITED_EVENT, 0),
            calculated_at=now_utc,
        ),
        day_start_utc=day_start_utc,
        day_end_utc=day_end_utc,
    )
