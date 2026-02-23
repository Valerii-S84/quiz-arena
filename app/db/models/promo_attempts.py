from __future__ import annotations

from datetime import datetime

from sqlalchemy import CHAR, BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class PromoAttempt(Base):
    __tablename__ = "promo_attempts"
    __table_args__ = (
        CheckConstraint(
            "result IN ('ACCEPTED','INVALID','EXPIRED','NOT_APPLICABLE','RATE_LIMITED')",
            name="ck_promo_attempts_result",
        ),
        CheckConstraint("source IN ('COMMAND','BUTTON','API')", name="ck_promo_attempts_source"),
        Index("idx_promo_attempts_user_time", "user_id", "attempted_at"),
        Index("idx_promo_attempts_code_time", "normalized_code_hash", "attempted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    normalized_code_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    result: Mapped[str] = mapped_column(String(24), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
