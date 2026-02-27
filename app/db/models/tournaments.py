from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class Tournament(Base):
    __tablename__ = "tournaments"
    __table_args__ = (
        CheckConstraint("type IN ('PRIVATE','DAILY_ARENA')", name="ck_tournaments_type"),
        CheckConstraint(
            "status IN ('REGISTRATION','ROUND_1','ROUND_2','ROUND_3','COMPLETED','CANCELED')",
            name="ck_tournaments_status",
        ),
        CheckConstraint("format IN ('QUICK_5','QUICK_12')", name="ck_tournaments_format"),
        CheckConstraint(
            "max_participants >= 2 AND max_participants <= 8",
            name="ck_tournaments_max_participants_range",
        ),
        CheckConstraint(
            "current_round >= 0 AND current_round <= 3",
            name="ck_tournaments_current_round_range",
        ),
        Index(
            "idx_tournaments_status_registration_deadline",
            "status",
            "registration_deadline",
        ),
        Index("idx_tournaments_status_round_deadline", "status", "round_deadline"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    max_participants: Mapped[int] = mapped_column(Integer, nullable=False)
    current_round: Mapped[int] = mapped_column(Integer, nullable=False)
    registration_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    round_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invite_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
