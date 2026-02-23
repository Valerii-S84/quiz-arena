from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class Entitlement(Base):
    __tablename__ = "entitlements"
    __table_args__ = (
        CheckConstraint(
            "entitlement_type IN ('PREMIUM','MODE_ACCESS','STREAK_SAVER_TOKEN','PREMIUM_AUTO_FREEZE')",
            name="ck_entitlements_type",
        ),
        CheckConstraint(
            "status IN ('SCHEDULED','ACTIVE','EXPIRED','CONSUMED','REVOKED')",
            name="ck_entitlements_status",
        ),
        Index("idx_entitlements_user_type", "user_id", "entitlement_type"),
        Index("idx_entitlements_starts", "starts_at"),
        Index("idx_entitlements_ends", "ends_at"),
        Index("idx_entitlements_purchase", "source_purchase_id"),
        Index(
            "uq_entitlements_active_premium_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("entitlement_type = 'PREMIUM' AND status = 'ACTIVE'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    entitlement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_purchase_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("purchases.id"),
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(96), unique=True, nullable=False)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
