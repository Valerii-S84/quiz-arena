from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class ModeProgress(Base):
    __tablename__ = "mode_progress"
    __table_args__ = (
        CheckConstraint(
            "preferred_level IN ('A1','A2','B1','B2','C1','C2')",
            name="ck_mode_progress_preferred_level",
        ),
        Index("idx_mode_progress_mode", "mode_code"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), primary_key=True)
    mode_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    preferred_level: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
