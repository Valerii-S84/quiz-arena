from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    __table_args__ = (
        CheckConstraint(
            "source IN ('BOT','WORKER','API','SYSTEM')",
            name="ck_analytics_events_source",
        ),
        Index("idx_analytics_events_created_at", "created_at"),
        Index("idx_analytics_events_type_time", "event_type", "happened_at"),
        Index("idx_analytics_events_user_time", "user_id", "happened_at"),
        Index("idx_analytics_events_local_date_type", "local_date_berlin", "event_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    local_date_berlin: Mapped[date] = mapped_column(Date, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    happened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
