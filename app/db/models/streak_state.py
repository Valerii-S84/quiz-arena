from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class StreakState(Base):
    __tablename__ = "streak_state"
    __table_args__ = (
        CheckConstraint("current_streak >= 0", name="ck_streak_state_current_streak_non_negative"),
        CheckConstraint("best_streak >= 0", name="ck_streak_state_best_streak_non_negative"),
        CheckConstraint("streak_saver_tokens >= 0", name="ck_streak_state_tokens_non_negative"),
        CheckConstraint(
            "today_status IN ('NO_ACTIVITY','PLAYED','FROZEN')",
            name="ck_streak_state_today_status",
        ),
        Index("idx_streak_last_activity", "last_activity_local_date"),
        Index("idx_streak_saver_purchase", "streak_saver_last_purchase_at"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), primary_key=True)
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False)
    best_streak: Mapped[int] = mapped_column(Integer, nullable=False)
    last_activity_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    today_status: Mapped[str] = mapped_column(String(16), nullable=False)
    streak_saver_tokens: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    streak_saver_last_purchase_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    premium_freezes_used_week: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    premium_freeze_week_start_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
