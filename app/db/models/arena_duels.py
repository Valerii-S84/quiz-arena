from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class ArenaDuel(Base):
    __tablename__ = "arena_duels"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','ACTIVE','EXPIRED','CANCELLED')",
            name="ck_arena_duels_status",
        ),
        CheckConstraint(
            "jsonb_typeof(question_ids) = 'array' AND jsonb_array_length(question_ids) = 7",
            name="ck_arena_duels_question_ids_7",
        ),
        Index("idx_arena_duels_creator_created", "creator_user_id", "created_at"),
        Index("idx_arena_duels_status_expires_created", "status", "expires_at", "created_at"),
        Index("idx_arena_duels_source_friend", "source_friend_challenge_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    creator_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    baseline_attempt_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "arena_attempts.id",
            name="fk_arena_duels_baseline_attempt_id_arena_attempts",
            use_alter=True,
        ),
        nullable=True,
    )
    question_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    mode_code: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_friend_challenge_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("friend_challenges.id"),
        nullable=True,
    )


class ArenaAttempt(Base):
    __tablename__ = "arena_attempts"
    __table_args__ = (
        CheckConstraint(
            "role IN ('CREATOR_BASELINE','CHALLENGER')",
            name="ck_arena_attempts_role",
        ),
        CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 7)",
            name="ck_arena_attempts_score_range",
        ),
        CheckConstraint(
            "time_ms IS NULL OR time_ms >= 0",
            name="ck_arena_attempts_time_ms_non_negative",
        ),
        Index("idx_arena_attempts_duel", "arena_duel_id"),
        Index("idx_arena_attempts_user", "user_id"),
        Index("uq_arena_attempts_duel_user", "arena_duel_id", "user_id", unique=True),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    arena_duel_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("arena_duels.id"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
