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
        CheckConstraint("purchase_rate >= 0 AND purchase_rate <= 1", name="ck_analytics_daily_purchase_rate"),
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
    purchases_credited_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    purchasers_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    purchase_rate: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False, server_default=text("0"))
    promo_redemptions_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
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
    quiz_sessions_started_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    quiz_sessions_completed_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    gameplay_completion_rate: Mapped[float] = mapped_column(
        Numeric(8, 6),
        nullable=False,
        server_default=text("0"),
    )
    energy_zero_events_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    streak_lost_events_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
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
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
