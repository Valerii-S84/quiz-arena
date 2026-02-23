from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_ledger_entries_amount_positive"),
        CheckConstraint(
            "asset IN ('FREE_ENERGY','PAID_ENERGY','PREMIUM','MODE_ACCESS','STREAK_SAVER')",
            name="ck_ledger_entries_asset",
        ),
        CheckConstraint("direction IN ('CREDIT','DEBIT')", name="ck_ledger_entries_direction"),
        Index("idx_ledger_user_created", "user_id", "created_at"),
        Index("idx_ledger_purchase", "purchase_id"),
        Index("idx_ledger_type", "entry_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    purchase_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("purchases.id"),
        nullable=True,
    )
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(96), unique=True, nullable=False)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
