from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('CREATED','VALIDATED','RESERVED','APPLIED','EXPIRED','REJECTED','REVOKED')",
            name="ck_promo_redemptions_status",
        ),
        UniqueConstraint("promo_code_id", "user_id", name="uq_promo_redemptions_code_user"),
        Index("idx_promo_redemptions_code", "promo_code_id"),
        Index("idx_promo_redemptions_user", "user_id"),
        Index("idx_promo_redemptions_reserved_until", "reserved_until"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    promo_code_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("promo_codes.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reject_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reserved_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_purchase_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("purchases.id"),
        unique=True,
        nullable=True,
    )
    grant_entitlement_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("entitlements.id"),
        unique=True,
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(96), unique=True, nullable=False)
    validation_snapshot: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
