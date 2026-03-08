from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BOOLEAN,
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class PromoCode(Base):
    __tablename__ = "promo_codes"
    __table_args__ = (
        CheckConstraint(
            "promo_type IN ('PREMIUM_GRANT','PERCENT_DISCOUNT')",
            name="ck_promo_codes_type",
        ),
        CheckConstraint(
            "grant_premium_days IS NULL OR grant_premium_days IN (7,30,90)",
            name="ck_promo_codes_grant_days",
        ),
        CheckConstraint(
            "discount_percent IS NULL OR (discount_percent BETWEEN 1 AND 100)",
            name="ck_promo_codes_discount_percent",
        ),
        CheckConstraint(
            "discount_type IS NULL OR discount_type IN ('PERCENT','FIXED','FREE')",
            name="ck_promo_codes_discount_type",
        ),
        CheckConstraint(
            "status IN ('ACTIVE','PAUSED','EXPIRED','DEPLETED')",
            name="ck_promo_codes_status",
        ),
        CheckConstraint(
            "max_total_uses IS NULL OR max_total_uses > 0",
            name="ck_promo_codes_max_total_uses_positive",
        ),
        CheckConstraint("used_total >= 0", name="ck_promo_codes_used_total_non_negative"),
        CheckConstraint("max_uses_per_user > 0", name="ck_promo_codes_max_uses_per_user_positive"),
        CheckConstraint(
            "((promo_type = 'PREMIUM_GRANT' AND grant_premium_days IS NOT NULL AND discount_percent IS NULL "
            "AND discount_type IS NULL AND discount_value IS NULL) "
            "OR (promo_type = 'PERCENT_DISCOUNT' AND grant_premium_days IS NULL "
            "AND ((discount_type IS NULL AND discount_percent IS NOT NULL) "
            "OR (discount_type = 'PERCENT' AND discount_value IS NOT NULL AND discount_value BETWEEN 1 AND 100) "
            "OR (discount_type = 'FIXED' AND discount_value IS NOT NULL AND discount_value > 0) "
            "OR (discount_type = 'FREE' AND discount_value IS NULL))))",
            name="ck_promo_codes_type_payload_consistency",
        ),
        CheckConstraint(
            "max_total_uses IS NULL OR used_total <= max_total_uses",
            name="ck_promo_codes_used_total_le_max",
        ),
        Index("idx_promo_codes_prefix", "code_prefix"),
        Index("idx_promo_codes_target", "target_scope"),
        Index("idx_promo_codes_valid_from", "valid_from"),
        Index("idx_promo_codes_valid_until", "valid_until"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code_hash: Mapped[str] = mapped_column(CHAR(64), unique=True, nullable=False)
    code_prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    code_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    campaign_name: Mapped[str] = mapped_column(String(128), nullable=False)
    promo_type: Mapped[str] = mapped_column(String(32), nullable=False)
    grant_premium_days: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    discount_percent: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    discount_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    discount_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    applicable_products: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    target_scope: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_total_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_uses_per_user: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("1")
    )
    new_users_only: Mapped[bool] = mapped_column(
        BOOLEAN, nullable=False, server_default=text("false")
    )
    first_purchase_only: Mapped[bool] = mapped_column(
        BOOLEAN, nullable=False, server_default=text("false")
    )
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
