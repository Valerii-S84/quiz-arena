from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class AdminPromoCode(Base):
    __tablename__ = "admin_promo_codes"
    __table_args__ = (
        CheckConstraint(
            "promo_type IN ('discount_percent','discount_stars','bonus_energy','bonus_subscription_days','free_product')",  # noqa: E501
            name="ck_admin_promo_codes_type",
        ),
        CheckConstraint(
            "status IN ('active','paused','expired','archived')",
            name="ck_admin_promo_codes_status",
        ),
        CheckConstraint("value >= 0", name="ck_admin_promo_codes_value_non_negative"),
        CheckConstraint("max_uses >= 0", name="ck_admin_promo_codes_max_uses_non_negative"),
        CheckConstraint("uses_count >= 0", name="ck_admin_promo_codes_uses_non_negative"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    promo_type: Mapped[str] = mapped_column(String(30), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    product_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    uses_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    channel_tag: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
