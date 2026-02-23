from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class AnalyticsDailyUpsert:
    local_date_berlin: date
    dau: int
    wau: int
    mau: int
    purchases_credited_total: int
    purchasers_total: int
    purchase_rate: float
    promo_redemptions_total: int
    promo_redemptions_applied_total: int
    promo_redemption_rate: float
    promo_to_paid_conversions_total: int
    quiz_sessions_started_total: int
    quiz_sessions_completed_total: int
    gameplay_completion_rate: float
    energy_zero_events_total: int
    streak_lost_events_total: int
    referral_reward_milestone_events_total: int
    referral_reward_granted_events_total: int
    purchase_init_events_total: int
    purchase_invoice_sent_events_total: int
    purchase_precheckout_ok_events_total: int
    purchase_paid_uncredited_events_total: int
    purchase_credited_events_total: int
    calculated_at: datetime
