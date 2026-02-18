from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class Purchase(Base):
    __tablename__ = "purchases"
    __table_args__ = (
        CheckConstraint(
            "product_type IN ('MICRO','PREMIUM','OFFER','REFERRAL_REWARD')",
            name="ck_purchases_product_type",
        ),
        CheckConstraint("base_stars_amount > 0", name="ck_purchases_base_amount_positive"),
        CheckConstraint("discount_stars_amount >= 0", name="ck_purchases_discount_non_negative"),
        CheckConstraint("stars_amount > 0", name="ck_purchases_stars_amount_positive"),
        CheckConstraint(
            "status IN ('CREATED','INVOICE_SENT','PRECHECKOUT_OK','PAID_UNCREDITED','CREDITED',"
            "'FAILED','FAILED_CREDIT_PENDING_REVIEW','REFUNDED')",
            name="ck_purchases_status",
        ),
        CheckConstraint(
            "stars_amount = GREATEST(1, base_stars_amount - discount_stars_amount)",
            name="ck_purchases_final_amount",
        ),
        Index("idx_purchases_user_created", "user_id", "created_at"),
        Index("idx_purchases_product", "product_code"),
        Index("idx_purchases_promo_code", "applied_promo_code_id"),
        Index(
            "uq_purchases_active_invoice_user_product",
            "user_id",
            "product_code",
            unique=True,
            postgresql_where=text("status IN ('CREATED','INVOICE_SENT','PRECHECKOUT_OK')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    product_code: Mapped[str] = mapped_column(String(32), nullable=False)
    product_type: Mapped[str] = mapped_column(String(16), nullable=False)
    base_stars_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_stars_amount: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    stars_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'XTR'"))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    applied_promo_code_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("promo_codes.id"),
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    invoice_payload: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    telegram_payment_charge_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    telegram_pre_checkout_query_id: Mapped[str | None] = mapped_column(
        String(128),
        unique=True,
        nullable=True,
    )
    raw_successful_payment: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    credited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
