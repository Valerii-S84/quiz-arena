from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Index, Integer, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class AnalyticsDaily(Base):
    __tablename__ = "analytics_daily"
    __table_args__ = (
        CheckConstraint("dau >= 0", name="ck_analytics_daily_dau_non_negative"),
        CheckConstraint("wau >= 0", name="ck_analytics_daily_wau_non_negative"),
        CheckConstraint("mau >= 0", name="ck_analytics_daily_mau_non_negative"),
        CheckConstraint(
            "purchases_credited_total >= 0",
            name="ck_analytics_daily_purchases_credited_non_negative",
        ),
        CheckConstraint("purchasers_total >= 0", name="ck_analytics_daily_purchasers_non_negative"),
        CheckConstraint(
            "promo_redemptions_total >= 0",
            name="ck_analytics_daily_promo_redemptions_non_negative",
        ),
        CheckConstraint(
            "promo_redemptions_applied_total >= 0",
            name="ck_analytics_daily_promo_redemptions_applied_non_negative",
        ),
        CheckConstraint(
            "promo_to_paid_conversions_total >= 0",
            name="ck_analytics_daily_promo_to_paid_non_negative",
        ),
        CheckConstraint(
            "quiz_sessions_started_total >= 0",
            name="ck_analytics_daily_sessions_started_non_negative",
        ),
        CheckConstraint(
            "quiz_sessions_completed_total >= 0",
            name="ck_analytics_daily_sessions_completed_non_negative",
        ),
        CheckConstraint(
            "energy_zero_events_total >= 0",
            name="ck_analytics_daily_energy_zero_non_negative",
        ),
        CheckConstraint(
            "streak_lost_events_total >= 0",
            name="ck_analytics_daily_streak_lost_non_negative",
        ),
        CheckConstraint(
            "referral_reward_milestone_events_total >= 0",
            name="ck_analytics_daily_referral_milestone_non_negative",
        ),
        CheckConstraint(
            "referral_reward_granted_events_total >= 0",
            name="ck_analytics_daily_referral_granted_non_negative",
        ),
        CheckConstraint(
            "purchase_init_events_total >= 0",
            name="ck_analytics_daily_purchase_init_events_non_negative",
        ),
        CheckConstraint(
            "purchase_invoice_sent_events_total >= 0",
            name="ck_analytics_daily_purchase_invoice_sent_events_non_negative",
        ),
        CheckConstraint(
            "purchase_precheckout_ok_events_total >= 0",
            name="ck_analytics_daily_purchase_precheckout_ok_events_non_negative",
        ),
        CheckConstraint(
            "purchase_paid_uncredited_events_total >= 0",
            name="ck_analytics_daily_purchase_paid_uncredited_events_non_negative",
        ),
        CheckConstraint(
            "purchase_credited_events_total >= 0",
            name="ck_analytics_daily_purchase_credited_events_non_negative",
        ),
        CheckConstraint(
            "duel_menu_opened_events_total >= 0",
            name="ck_analytics_daily_duel_menu_opened_non_negative",
        ),
        CheckConstraint(
            "duel_mode_selected_events_total >= 0",
            name="ck_analytics_daily_duel_mode_selected_non_negative",
        ),
        CheckConstraint(
            "arena_opened_events_total >= 0",
            name="ck_analytics_daily_arena_opened_non_negative",
        ),
        CheckConstraint(
            "arena_duel_created_events_total >= 0",
            name="ck_analytics_daily_arena_duel_created_non_negative",
        ),
        CheckConstraint(
            "arena_duel_started_events_total >= 0",
            name="ck_analytics_daily_arena_duel_started_non_negative",
        ),
        CheckConstraint(
            "arena_duel_completed_events_total >= 0",
            name="ck_analytics_daily_arena_duel_completed_non_negative",
        ),
        CheckConstraint(
            "arena_duel_published_events_total >= 0",
            name="ck_analytics_daily_arena_duel_published_non_negative",
        ),
        CheckConstraint(
            "arena_duel_accepted_events_total >= 0",
            name="ck_analytics_daily_arena_duel_accepted_non_negative",
        ),
        CheckConstraint(
            "arena_result_shown_events_total >= 0",
            name="ck_analytics_daily_arena_result_shown_non_negative",
        ),
        CheckConstraint(
            "arena_result_beaten_notification_sent_events_total >= 0",
            name="ck_analytics_daily_arena_beaten_notice_non_negative",
        ),
        CheckConstraint(
            "arena_revanche_clicked_events_total >= 0",
            name="ck_analytics_daily_arena_revanche_clicked_non_negative",
        ),
        CheckConstraint(
            "friend_duel_opened_events_total >= 0",
            name="ck_analytics_daily_friend_duel_opened_non_negative",
        ),
        CheckConstraint(
            "friend_duel_created_events_total >= 0",
            name="ck_analytics_daily_friend_duel_created_non_negative",
        ),
        CheckConstraint(
            "friend_duel_share_clicked_events_total >= 0",
            name="ck_analytics_daily_friend_share_clicked_non_negative",
        ),
        CheckConstraint(
            "friend_duel_joined_events_total >= 0",
            name="ck_analytics_daily_friend_duel_joined_non_negative",
        ),
        CheckConstraint(
            "friend_duel_started_events_total >= 0",
            name="ck_analytics_daily_friend_duel_started_non_negative",
        ),
        CheckConstraint(
            "friend_duel_completed_events_total >= 0",
            name="ck_analytics_daily_friend_duel_completed_non_negative",
        ),
        CheckConstraint(
            "friend_duel_published_to_arena_events_total >= 0",
            name="ck_analytics_daily_friend_publish_arena_non_negative",
        ),
        CheckConstraint(
            "friend_duel_revanche_clicked_events_total >= 0",
            name="ck_analytics_daily_friend_revanche_clicked_non_negative",
        ),
        CheckConstraint(
            "duel_limit_hit_events_total >= 0",
            name="ck_analytics_daily_duel_limit_hit_non_negative",
        ),
        CheckConstraint(
            "duel_paywall_shown_events_total >= 0",
            name="ck_analytics_daily_duel_paywall_shown_non_negative",
        ),
        CheckConstraint(
            "duel_ticket_clicked_events_total >= 0",
            name="ck_analytics_daily_duel_ticket_clicked_non_negative",
        ),
        CheckConstraint(
            "premium_week_clicked_events_total >= 0",
            name="ck_analytics_daily_premium_week_clicked_non_negative",
        ),
        CheckConstraint(
            "purchase_rate >= 0 AND purchase_rate <= 1",
            name="ck_analytics_daily_purchase_rate",
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

    local_date_berlin: Mapped[date] = mapped_column(Date, primary_key=True)
    dau: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    wau: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    mau: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    purchases_credited_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    purchasers_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    purchase_rate: Mapped[float] = mapped_column(
        Numeric(8, 6), nullable=False, server_default=text("0")
    )
    promo_redemptions_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    promo_redemptions_applied_total: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    promo_redemption_rate: Mapped[float] = mapped_column(
        Numeric(8, 6),
        nullable=False,
        server_default=text("0"),
    )
    promo_to_paid_conversions_total: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    quiz_sessions_started_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    quiz_sessions_completed_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    gameplay_completion_rate: Mapped[float] = mapped_column(
        Numeric(8, 6),
        nullable=False,
        server_default=text("0"),
    )
    energy_zero_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    streak_lost_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    referral_reward_milestone_events_total: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    referral_reward_granted_events_total: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    purchase_init_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    purchase_invoice_sent_events_total: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    purchase_precheckout_ok_events_total: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    purchase_paid_uncredited_events_total: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    purchase_credited_events_total: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    duel_menu_opened_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    duel_mode_selected_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    arena_opened_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    arena_duel_created_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    arena_duel_started_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    arena_duel_completed_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    arena_duel_published_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    arena_duel_accepted_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    arena_result_shown_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    arena_result_beaten_notification_sent_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    arena_revanche_clicked_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    friend_duel_opened_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    friend_duel_created_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    friend_duel_share_clicked_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    friend_duel_joined_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    friend_duel_started_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    friend_duel_completed_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    friend_duel_published_to_arena_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    friend_duel_revanche_clicked_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    duel_limit_hit_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    duel_paywall_shown_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    duel_ticket_clicked_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    premium_week_clicked_events_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
