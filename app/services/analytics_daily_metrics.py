from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.analytics_repo import AnalyticsDailyUpsert, AnalyticsRepo
from app.services.analytics_daily_events import (
    ENERGY_ZERO_EVENT,
    PURCHASE_CREDITED_EVENT,
    PURCHASE_INIT_EVENT,
    PURCHASE_INVOICE_SENT_EVENT,
    PURCHASE_PAID_UNCREDITED_EVENT,
    PURCHASE_PRECHECKOUT_OK_EVENT,
    REFERRAL_REWARD_GRANTED_EVENT,
    REFERRAL_REWARD_MILESTONE_EVENT,
    STREAK_LOST_EVENT,
    duel_funnel_counts,
)


@dataclass(frozen=True, slots=True)
class ActivityMetrics:
    dau: int
    wau: int
    mau: int


@dataclass(frozen=True, slots=True)
class PurchaseMetrics:
    credited_total: int
    purchasers_total: int
    promo_to_paid_conversions_total: int


@dataclass(frozen=True, slots=True)
class PromoMetrics:
    redemptions_total: int
    redemptions_applied_total: int


@dataclass(frozen=True, slots=True)
class QuizMetrics:
    sessions_started_total: int
    sessions_completed_total: int


def safe_rate(*, numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


async def collect_purchase_metrics(
    session: AsyncSession,
    *,
    day_start_utc: datetime,
    day_end_utc: datetime,
) -> PurchaseMetrics:
    return PurchaseMetrics(
        credited_total=await AnalyticsRepo.count_credited_purchases_between(
            session,
            from_utc=day_start_utc,
            to_utc=day_end_utc,
        ),
        purchasers_total=await AnalyticsRepo.count_distinct_credited_purchasers_between(
            session,
            from_utc=day_start_utc,
            to_utc=day_end_utc,
        ),
        promo_to_paid_conversions_total=(
            await AnalyticsRepo.count_promo_to_paid_conversions_between(
                session,
                from_utc=day_start_utc,
                to_utc=day_end_utc,
            )
        ),
    )


async def collect_promo_metrics(
    session: AsyncSession,
    *,
    day_start_utc: datetime,
    day_end_utc: datetime,
) -> PromoMetrics:
    return PromoMetrics(
        redemptions_total=await AnalyticsRepo.count_promo_redemptions_between(
            session,
            from_utc=day_start_utc,
            to_utc=day_end_utc,
        ),
        redemptions_applied_total=await AnalyticsRepo.count_applied_promo_redemptions_between(
            session,
            from_utc=day_start_utc,
            to_utc=day_end_utc,
        ),
    )


async def collect_quiz_metrics(
    session: AsyncSession,
    *,
    day_start_utc: datetime,
    day_end_utc: datetime,
) -> QuizMetrics:
    return QuizMetrics(
        sessions_started_total=await AnalyticsRepo.count_quiz_sessions_started_between(
            session,
            from_utc=day_start_utc,
            to_utc=day_end_utc,
        ),
        sessions_completed_total=await AnalyticsRepo.count_quiz_sessions_completed_between(
            session,
            from_utc=day_start_utc,
            to_utc=day_end_utc,
        ),
    )


def build_daily_upsert(
    *,
    local_date_berlin: date,
    now_utc: datetime,
    activity: ActivityMetrics,
    purchases: PurchaseMetrics,
    promo: PromoMetrics,
    quiz: QuizMetrics,
    event_counts: dict[str, int],
) -> AnalyticsDailyUpsert:
    return AnalyticsDailyUpsert(
        local_date_berlin=local_date_berlin,
        dau=activity.dau,
        wau=activity.wau,
        mau=activity.mau,
        purchases_credited_total=purchases.credited_total,
        purchasers_total=purchases.purchasers_total,
        purchase_rate=safe_rate(numerator=purchases.purchasers_total, denominator=activity.dau),
        promo_redemptions_total=promo.redemptions_total,
        promo_redemptions_applied_total=promo.redemptions_applied_total,
        promo_redemption_rate=safe_rate(
            numerator=promo.redemptions_applied_total,
            denominator=promo.redemptions_total,
        ),
        promo_to_paid_conversions_total=purchases.promo_to_paid_conversions_total,
        quiz_sessions_started_total=quiz.sessions_started_total,
        quiz_sessions_completed_total=quiz.sessions_completed_total,
        gameplay_completion_rate=safe_rate(
            numerator=quiz.sessions_completed_total,
            denominator=quiz.sessions_started_total,
        ),
        energy_zero_events_total=event_counts.get(ENERGY_ZERO_EVENT, 0),
        streak_lost_events_total=event_counts.get(STREAK_LOST_EVENT, 0),
        referral_reward_milestone_events_total=event_counts.get(REFERRAL_REWARD_MILESTONE_EVENT, 0),
        referral_reward_granted_events_total=event_counts.get(REFERRAL_REWARD_GRANTED_EVENT, 0),
        purchase_init_events_total=event_counts.get(PURCHASE_INIT_EVENT, 0),
        purchase_invoice_sent_events_total=event_counts.get(PURCHASE_INVOICE_SENT_EVENT, 0),
        purchase_precheckout_ok_events_total=event_counts.get(PURCHASE_PRECHECKOUT_OK_EVENT, 0),
        purchase_paid_uncredited_events_total=event_counts.get(PURCHASE_PAID_UNCREDITED_EVENT, 0),
        purchase_credited_events_total=event_counts.get(PURCHASE_CREDITED_EVENT, 0),
        **duel_funnel_counts(event_counts),
        calculated_at=now_utc,
    )
