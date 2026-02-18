from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class QuizSession(Base):
    __tablename__ = "quiz_sessions"
    __table_args__ = (
        CheckConstraint(
            "source IN ('MENU','DAILY_CHALLENGE','FRIEND_CHALLENGE','TOURNAMENT')",
            name="ck_quiz_sessions_source",
        ),
        CheckConstraint(
            "status IN ('STARTED','COMPLETED','ABANDONED','CANCELED')",
            name="ck_quiz_sessions_status",
        ),
        CheckConstraint("energy_cost_total >= 0", name="ck_quiz_sessions_energy_cost_non_negative"),
        Index("idx_sessions_user_started", "user_id", "started_at"),
        Index("idx_sessions_mode", "mode_code"),
        Index("idx_sessions_local_date", "local_date_berlin"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    mode_code: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    energy_cost_total: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    local_date_berlin: Mapped[date] = mapped_column(Date, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(96), unique=True, nullable=False)
