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
    duel_menu_opened_events_total: int
    duel_mode_selected_events_total: int
    arena_opened_events_total: int
    arena_duel_created_events_total: int
    arena_duel_started_events_total: int
    arena_duel_completed_events_total: int
    arena_duel_published_events_total: int
    arena_duel_accepted_events_total: int
    arena_result_shown_events_total: int
    arena_result_beaten_notification_sent_events_total: int
    arena_revanche_clicked_events_total: int
    friend_duel_opened_events_total: int
    friend_duel_created_events_total: int
    friend_duel_share_clicked_events_total: int
    friend_duel_joined_events_total: int
    friend_duel_started_events_total: int
    friend_duel_completed_events_total: int
    friend_duel_published_to_arena_events_total: int
    friend_duel_revanche_clicked_events_total: int
    duel_limit_hit_events_total: int
    duel_paywall_shown_events_total: int
    duel_ticket_clicked_events_total: int
    premium_week_clicked_events_total: int
    calculated_at: datetime
