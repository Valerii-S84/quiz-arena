from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class ProcessedUpdate(Base):
    __tablename__ = "processed_updates"
    __table_args__ = (
        Index("idx_processed_updates_processed_at", "processed_at"),
        Index(
            "idx_processed_updates_processing_status_age",
            "processed_at",
            postgresql_where=text("status = 'PROCESSING'"),
        ),
    )

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    processing_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
