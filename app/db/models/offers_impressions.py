from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class OfferImpression(Base):
    __tablename__ = "offers_impressions"
    __table_args__ = (
        Index("idx_offers_user_time", "user_id", "shown_at"),
        Index("idx_offers_code", "offer_code"),
        Index("idx_offers_local_date", "local_date_berlin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    offer_code: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_code: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    shown_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    local_date_berlin: Mapped[date] = mapped_column(Date, nullable=False)
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    converted_purchase_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("purchases.id"),
        nullable=True,
    )
    dismiss_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(96), unique=True, nullable=False)
