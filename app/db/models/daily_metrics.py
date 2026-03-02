from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, Date, Integer, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class DailyMetrics(Base):
    __tablename__ = "daily_metrics"
    __table_args__ = (
        CheckConstraint("dau >= 0", name="ck_daily_metrics_dau_non_negative"),
        CheckConstraint("wau >= 0", name="ck_daily_metrics_wau_non_negative"),
        CheckConstraint("mau >= 0", name="ck_daily_metrics_mau_non_negative"),
        CheckConstraint("new_users >= 0", name="ck_daily_metrics_new_users_non_negative"),
        CheckConstraint(
            "revenue_stars >= 0",
            name="ck_daily_metrics_revenue_stars_non_negative",
        ),
        CheckConstraint("revenue_eur >= 0", name="ck_daily_metrics_revenue_eur_non_negative"),
        CheckConstraint("quizzes_played >= 0", name="ck_daily_metrics_quizzes_non_negative"),
        CheckConstraint(
            "purchases_count >= 0",
            name="ck_daily_metrics_purchases_non_negative",
        ),
        CheckConstraint(
            "active_subscriptions >= 0",
            name="ck_daily_metrics_active_subscriptions_non_negative",
        ),
    )

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    dau: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    wau: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    mau: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    new_users: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    revenue_stars: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    revenue_eur: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, server_default=text("0")
    )
    quizzes_played: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    purchases_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    active_subscriptions: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
