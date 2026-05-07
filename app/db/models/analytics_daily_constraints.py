from __future__ import annotations

from sqlalchemy import CheckConstraint, Index


def _non_negative(column: str, name: str) -> CheckConstraint:
    return CheckConstraint(f"{column} >= 0", name=name)


ANALYTICS_DAILY_TABLE_ARGS = (
    _non_negative("dau", "ck_analytics_daily_dau_non_negative"),
    _non_negative("wau", "ck_analytics_daily_wau_non_negative"),
    _non_negative("mau", "ck_analytics_daily_mau_non_negative"),
    _non_negative("purchases_credited_total", "ck_analytics_daily_purchases_credited_non_negative"),
    _non_negative("purchasers_total", "ck_analytics_daily_purchasers_non_negative"),
    _non_negative("promo_redemptions_total", "ck_analytics_daily_promo_redemptions_non_negative"),
    _non_negative(
        "promo_redemptions_applied_total",
        "ck_analytics_daily_promo_redemptions_applied_non_negative",
    ),
    _non_negative(
        "promo_to_paid_conversions_total", "ck_analytics_daily_promo_to_paid_non_negative"
    ),
    _non_negative(
        "quiz_sessions_started_total", "ck_analytics_daily_sessions_started_non_negative"
    ),
    _non_negative(
        "quiz_sessions_completed_total", "ck_analytics_daily_sessions_completed_non_negative"
    ),
    _non_negative("energy_zero_events_total", "ck_analytics_daily_energy_zero_non_negative"),
    _non_negative("streak_lost_events_total", "ck_analytics_daily_streak_lost_non_negative"),
    _non_negative(
        "referral_reward_milestone_events_total",
        "ck_analytics_daily_referral_milestone_non_negative",
    ),
    _non_negative(
        "referral_reward_granted_events_total", "ck_analytics_daily_referral_granted_non_negative"
    ),
    _non_negative(
        "purchase_init_events_total", "ck_analytics_daily_purchase_init_events_non_negative"
    ),
    _non_negative(
        "purchase_invoice_sent_events_total",
        "ck_analytics_daily_purchase_invoice_sent_events_non_negative",
    ),
    _non_negative(
        "purchase_precheckout_ok_events_total",
        "ck_analytics_daily_purchase_precheckout_ok_events_non_negative",
    ),
    _non_negative(
        "purchase_paid_uncredited_events_total",
        "ck_analytics_daily_purchase_paid_uncredited_events_non_negative",
    ),
    _non_negative(
        "purchase_credited_events_total", "ck_analytics_daily_purchase_credited_events_non_negative"
    ),
    _non_negative(
        "duel_menu_opened_events_total", "ck_analytics_daily_duel_menu_opened_non_negative"
    ),
    _non_negative(
        "duel_mode_selected_events_total", "ck_analytics_daily_duel_mode_selected_non_negative"
    ),
    _non_negative("arena_opened_events_total", "ck_analytics_daily_arena_opened_non_negative"),
    _non_negative(
        "arena_duel_created_events_total", "ck_analytics_daily_arena_duel_created_non_negative"
    ),
    _non_negative(
        "arena_duel_started_events_total", "ck_analytics_daily_arena_duel_started_non_negative"
    ),
    _non_negative(
        "arena_duel_completed_events_total", "ck_analytics_daily_arena_duel_completed_non_negative"
    ),
    _non_negative(
        "arena_duel_published_events_total", "ck_analytics_daily_arena_duel_published_non_negative"
    ),
    _non_negative(
        "arena_duel_accepted_events_total", "ck_analytics_daily_arena_duel_accepted_non_negative"
    ),
    _non_negative(
        "arena_result_shown_events_total", "ck_analytics_daily_arena_result_shown_non_negative"
    ),
    _non_negative(
        "arena_result_beaten_notification_sent_events_total",
        "ck_analytics_daily_arena_beaten_notice_non_negative",
    ),
    _non_negative(
        "arena_revanche_clicked_events_total",
        "ck_analytics_daily_arena_revanche_clicked_non_negative",
    ),
    _non_negative(
        "friend_duel_opened_events_total", "ck_analytics_daily_friend_duel_opened_non_negative"
    ),
    _non_negative(
        "friend_duel_created_events_total", "ck_analytics_daily_friend_duel_created_non_negative"
    ),
    _non_negative(
        "friend_duel_share_clicked_events_total",
        "ck_analytics_daily_friend_share_clicked_non_negative",
    ),
    _non_negative(
        "friend_duel_joined_events_total", "ck_analytics_daily_friend_duel_joined_non_negative"
    ),
    _non_negative(
        "friend_duel_started_events_total", "ck_analytics_daily_friend_duel_started_non_negative"
    ),
    _non_negative(
        "friend_duel_completed_events_total",
        "ck_analytics_daily_friend_duel_completed_non_negative",
    ),
    _non_negative(
        "friend_duel_published_to_arena_events_total",
        "ck_analytics_daily_friend_publish_arena_non_negative",
    ),
    _non_negative(
        "friend_duel_revanche_clicked_events_total",
        "ck_analytics_daily_friend_revanche_clicked_non_negative",
    ),
    _non_negative("duel_limit_hit_events_total", "ck_analytics_daily_duel_limit_hit_non_negative"),
    _non_negative(
        "duel_paywall_shown_events_total", "ck_analytics_daily_duel_paywall_shown_non_negative"
    ),
    _non_negative(
        "duel_ticket_clicked_events_total", "ck_analytics_daily_duel_ticket_clicked_non_negative"
    ),
    _non_negative(
        "premium_week_clicked_events_total", "ck_analytics_daily_premium_week_clicked_non_negative"
    ),
    CheckConstraint(
        "purchase_rate >= 0 AND purchase_rate <= 1", name="ck_analytics_daily_purchase_rate"
    ),
    CheckConstraint(
        "promo_redemption_rate >= 0 AND promo_redemption_rate <= 1",
        name="ck_analytics_daily_promo_redemption_rate",
    ),
    CheckConstraint(
        "gameplay_completion_rate >= 0 AND gameplay_completion_rate <= 1",
        name="ck_analytics_daily_gameplay_completion_rate",
    ),
    Index("idx_analytics_daily_calculated_at", "calculated_at"),
)
