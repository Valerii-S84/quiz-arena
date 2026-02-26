from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class DailyRun(Base):
    __tablename__ = "daily_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('IN_PROGRESS','COMPLETED','ABANDONED')",
            name="ck_daily_runs_status",
        ),
        CheckConstraint(
            "current_question >= 0 AND current_question <= 7",
            name="ck_daily_runs_question_range",
        ),
        CheckConstraint(
            "score >= 0 AND score <= current_question AND score <= 7",
            name="ck_daily_runs_score_range",
        ),
        CheckConstraint(
            "(status != 'COMPLETED') OR completed_at IS NOT NULL",
            name="ck_daily_runs_completed_at_required",
        ),
        Index(
            "uq_daily_runs_user_date_completed",
            "user_id",
            "berlin_date",
            unique=True,
            postgresql_where=text("status = 'COMPLETED'"),
        ),
        Index("idx_daily_runs_berlin_date_status", "berlin_date", "status"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    berlin_date: Mapped[date] = mapped_column(Date, nullable=False)
    current_question: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    score: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
