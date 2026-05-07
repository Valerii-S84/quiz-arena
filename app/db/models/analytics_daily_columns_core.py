from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column


def _int_metric() -> Mapped[int]:
    return mapped_column(Integer, nullable=False, server_default=text("0"))


def _rate_metric() -> Mapped[float]:
    return mapped_column(Numeric(8, 6), nullable=False, server_default=text("0"))


class AnalyticsDailyCoreMetricsMixin:
    local_date_berlin: Mapped[date] = mapped_column(Date, primary_key=True)
    dau: Mapped[int] = _int_metric()
    wau: Mapped[int] = _int_metric()
    mau: Mapped[int] = _int_metric()
    purchases_credited_total: Mapped[int] = _int_metric()
    purchasers_total: Mapped[int] = _int_metric()
    purchase_rate: Mapped[float] = _rate_metric()
    promo_redemptions_total: Mapped[int] = _int_metric()
    promo_redemptions_applied_total: Mapped[int] = _int_metric()
    promo_redemption_rate: Mapped[float] = _rate_metric()
    promo_to_paid_conversions_total: Mapped[int] = _int_metric()
    quiz_sessions_started_total: Mapped[int] = _int_metric()
    quiz_sessions_completed_total: Mapped[int] = _int_metric()
    gameplay_completion_rate: Mapped[float] = _rate_metric()
    energy_zero_events_total: Mapped[int] = _int_metric()
    streak_lost_events_total: Mapped[int] = _int_metric()
    referral_reward_milestone_events_total: Mapped[int] = _int_metric()
    referral_reward_granted_events_total: Mapped[int] = _int_metric()
    purchase_init_events_total: Mapped[int] = _int_metric()
    purchase_invoice_sent_events_total: Mapped[int] = _int_metric()
    purchase_precheckout_ok_events_total: Mapped[int] = _int_metric()
    purchase_paid_uncredited_events_total: Mapped[int] = _int_metric()
    purchase_credited_events_total: Mapped[int] = _int_metric()
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
