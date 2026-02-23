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
        CheckConstraint(
            "(source != 'FRIEND_CHALLENGE') OR friend_challenge_id IS NOT NULL",
            name="ck_quiz_sessions_friend_source_link",
        ),
        CheckConstraint(
            "(friend_challenge_id IS NULL AND friend_challenge_round IS NULL) "
            "OR (friend_challenge_id IS NOT NULL AND friend_challenge_round >= 1)",
            name="ck_quiz_sessions_friend_round_consistency",
        ),
        Index("idx_sessions_user_started", "user_id", "started_at"),
        Index("idx_sessions_mode", "mode_code"),
        Index("idx_sessions_local_date", "local_date_berlin"),
        Index(
            "idx_sessions_friend_challenge",
            "friend_challenge_id",
            "friend_challenge_round",
        ),
        Index(
            "uq_daily_challenge_user_date",
            "user_id",
            "local_date_berlin",
            unique=True,
            postgresql_where=text("source = 'DAILY_CHALLENGE'"),
        ),
        Index(
            "uq_sessions_friend_challenge_user_round",
            "friend_challenge_id",
            "user_id",
            "friend_challenge_round",
            unique=True,
            postgresql_where=text("friend_challenge_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    mode_code: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    energy_cost_total: Mapped[int] = mapped_column(Integer, nullable=False)
    question_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    friend_challenge_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("friend_challenges.id"),
        nullable=True,
    )
    friend_challenge_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    local_date_berlin: Mapped[date] = mapped_column(Date, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(96), unique=True, nullable=False)
