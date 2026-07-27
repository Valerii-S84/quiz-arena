from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class ProductionInvariantAlert(Base):
    __tablename__ = "production_invariant_alerts"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('P0','P1','P2')",
            name="ck_production_invariant_alerts_severity",
        ),
        CheckConstraint(
            "status IN ('OPEN','RESOLVED','ACKED')",
            name="ck_production_invariant_alerts_status",
        ),
        Index("idx_production_invariant_alerts_status_seen", "status", "last_seen_at"),
        Index("idx_production_invariant_alerts_type_seen", "type", "last_seen_at"),
        Index(
            "uq_production_invariant_alerts_active_type_key",
            "type",
            "correlation_key",
            unique=True,
            postgresql_where=text("status = 'OPEN'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    type: Mapped[str] = mapped_column(String(96), nullable=False)
    correlation_key: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'OPEN'"),
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    safe_context: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
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
