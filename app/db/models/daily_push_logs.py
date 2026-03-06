from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class DailyPushLog(Base):
    __tablename__ = "daily_push_logs"
    __table_args__ = (
        CheckConstraint(
            "push_kind IN ('MORNING','EVENING_REMINDER')",
            name="ck_daily_push_logs_push_kind",
        ),
        Index("idx_daily_push_logs_berlin_date", "berlin_date"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        primary_key=True,
    )
    berlin_date: Mapped[date] = mapped_column(Date, primary_key=True)
    push_kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    push_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
