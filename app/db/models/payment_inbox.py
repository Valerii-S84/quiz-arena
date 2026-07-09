from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class TelegramUpdateInbox(Base):
    __tablename__ = "telegram_update_inbox"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_telegram_update_inbox_idempotency_key"),
        Index("idx_telegram_update_inbox_status_received", "status", "received_at"),
    )

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    update_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sanitized_evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'RECEIVED'")
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_payment_events_idempotency_key"),
        Index("idx_payment_events_status_created", "status", "created_at"),
        Index("idx_payment_events_invoice_payload", "invoice_payload"),
        Index("idx_payment_events_provider_charge_hash", "provider_charge_id_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'RECEIVED'")
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    source_inbox_update_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("telegram_update_inbox.update_id"),
        nullable=True,
    )
    purchase_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    invoice_payload: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_charge_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_payment_charge_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    total_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    safe_payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_type: Mapped[str | None] = mapped_column(String(128), nullable=True)


class PaymentReconciliationReview(Base):
    __tablename__ = "payment_reconciliation_reviews"
    __table_args__ = (
        UniqueConstraint("unique_key", name="uq_payment_reconciliation_reviews_unique_key"),
        Index("idx_payment_reconciliation_reviews_status_created", "status", "created_at"),
        Index("idx_payment_reconciliation_reviews_purchase", "purchase_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    unique_key: Mapped[str] = mapped_column(String(160), nullable=False)
    review_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'OPEN'"))
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    payment_event_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("payment_events.id"),
        nullable=True,
    )
    purchase_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    transaction_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    safe_payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
