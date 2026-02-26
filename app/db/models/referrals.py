from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('STARTED','QUALIFIED','REWARDED','REJECTED_FRAUD','CANCELED','DEFERRED_LIMIT')",
            name="ck_referrals_status",
        ),
        CheckConstraint(
            "referrer_user_id <> referred_user_id", name="ck_referrals_no_self_referral"
        ),
        UniqueConstraint(
            "referrer_user_id",
            "referred_user_id",
            name="uq_referrals_referrer_referred",
        ),
        Index("idx_referrals_referrer", "referrer_user_id"),
        Index("idx_referrals_code", "referral_code"),
        Index("idx_referrals_notified_at", "notified_at"),
        Index("idx_referrals_status_created", "status", "created_at"),
        Index(
            "idx_referrals_status_qualified_referrer",
            "status",
            "qualified_at",
            "referrer_user_id",
        ),
        Index(
            "idx_referrals_referrer_rewarded_at",
            "referrer_user_id",
            "rewarded_at",
            postgresql_where=text("status = 'REWARDED' AND rewarded_at IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    referrer_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    referred_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
    )
    referral_code: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    qualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rewarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fraud_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
