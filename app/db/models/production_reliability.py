from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class TelegramDeliveryAttempt(Base):
    __tablename__ = "telegram_delivery_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','SENT','FAILED','SKIPPED')",
            name="ck_telegram_delivery_attempts_status",
        ),
        Index("idx_telegram_delivery_flow_correlation", "flow", "correlation_id", "status"),
        Index("idx_telegram_delivery_target", "target_type", "target_id", "created_at"),
        Index(
            "idx_telegram_delivery_blocked_candidate",
            "status",
            "is_blocked_candidate",
            "failed_at",
            "id",
        ),
        Index(
            "idx_telegram_delivery_pending_claim",
            "flow",
            "created_at",
            "id",
            "attempt_count",
            "updated_at",
            postgresql_where=text("status = 'PENDING'"),
        ),
        UniqueConstraint(
            "idempotency_key",
            name="uq_telegram_delivery_attempts_idempotency_key",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    flow: Mapped[str] = mapped_column(String(64), nullable=False)
    task_name: Mapped[str] = mapped_column(String(160), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(160), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(220), nullable=False)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    chat_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'PENDING'"),
    )
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_error_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_blocked_candidate: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    safe_context: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class WorkerTaskHeartbeat(Base):
    __tablename__ = "worker_task_heartbeats"
    __table_args__ = (
        UniqueConstraint(
            "task_name",
            "schedule_key",
            name="uq_worker_task_heartbeats_task_schedule",
        ),
        Index("idx_worker_task_heartbeats_success", "last_success_at"),
        Index("idx_worker_task_heartbeats_failure", "last_failed_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    task_name: Mapped[str] = mapped_column(String(200), nullable=False)
    schedule_key: Mapped[str] = mapped_column(String(160), nullable=False)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_error_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
