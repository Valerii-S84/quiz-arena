from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class PromoAuditLog(Base):
    __tablename__ = "promo_audit_log"
    __table_args__ = (
        Index("idx_promo_audit_log_created_at", "created_at"),
        Index("idx_promo_audit_log_action", "action", "created_at"),
        Index("idx_promo_audit_log_promo_created_at", "promo_code_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    admin_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("admins.id"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    promo_code_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("promo_codes.id"),
        nullable=True,
    )
    details: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
