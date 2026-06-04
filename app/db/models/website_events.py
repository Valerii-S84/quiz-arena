from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class WebsiteEvent(Base):
    __tablename__ = "website_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('page_view','telegram_cta_click')",
            name="ck_website_events_event_type",
        ),
        Index("idx_website_events_created_at", "created_at"),
        Index("idx_website_events_local_date_type", "local_date_berlin", "event_type"),
        Index("idx_website_events_visitor_date", "visitor_hash", "local_date_berlin"),
        Index("idx_website_events_path_date", "path", "local_date_berlin"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    visitor_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    referrer: Mapped[str | None] = mapped_column(Text, nullable=True)
    utm_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    local_date_berlin: Mapped[date] = mapped_column(Date, nullable=False)
    event_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
