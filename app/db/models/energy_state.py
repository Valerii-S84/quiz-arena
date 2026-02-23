from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class EnergyState(Base):
    __tablename__ = "energy_state"
    __table_args__ = (
        CheckConstraint(
            "free_energy >= 0 AND free_energy <= 20",
            name="ck_energy_state_free_energy_range",
        ),
        CheckConstraint("paid_energy >= 0", name="ck_energy_state_paid_energy_non_negative"),
        Index("idx_energy_last_regen", "last_regen_at"),
        Index("idx_energy_topup_date", "last_daily_topup_local_date"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), primary_key=True)
    free_energy: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    paid_energy: Mapped[int] = mapped_column(Integer, nullable=False)
    free_cap: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=20)
    regen_interval_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=1800)
    last_regen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_daily_topup_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
