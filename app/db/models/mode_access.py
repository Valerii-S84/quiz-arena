from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class ModeAccess(Base):
    __tablename__ = "mode_access"
    __table_args__ = (
        CheckConstraint("source IN ('FREE','MEGA_PACK','PREMIUM')", name="ck_mode_access_source"),
        CheckConstraint("status IN ('ACTIVE','EXPIRED','REVOKED')", name="ck_mode_access_status"),
        UniqueConstraint(
            "user_id",
            "mode_code",
            "source",
            "starts_at",
            name="uq_mode_access_user_mode_source_starts",
        ),
        Index("idx_mode_access_user_mode", "user_id", "mode_code"),
        Index("idx_mode_access_mode", "mode_code"),
        Index("idx_mode_access_ends", "ends_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    mode_code: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    source_purchase_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("purchases.id"),
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(96), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
