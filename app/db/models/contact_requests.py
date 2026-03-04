from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class ContactRequest(Base):
    __tablename__ = "contact_requests"
    __table_args__ = (
        CheckConstraint(
            "request_type IN ('student','partner')",
            name="ck_contact_requests_type",
        ),
        CheckConstraint(
            "status IN ('NEW','IN_PROGRESS','DONE','SPAM')",
            name="ck_contact_requests_status",
        ),
        Index("idx_contact_requests_created_at", "created_at"),
        Index("idx_contact_requests_type_created", "request_type", "created_at"),
        Index("idx_contact_requests_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'NEW'"),
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
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
