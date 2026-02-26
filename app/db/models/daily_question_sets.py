from __future__ import annotations

from datetime import date

from sqlalchemy import CheckConstraint, Date, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class DailyQuestionSet(Base):
    __tablename__ = "daily_question_sets"
    __table_args__ = (
        CheckConstraint(
            "position >= 1 AND position <= 7",
            name="ck_daily_question_sets_position_range",
        ),
        Index("idx_daily_question_sets_question_id", "question_id"),
    )

    berlin_date: Mapped[date] = mapped_column(Date, primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[str] = mapped_column(String(64), nullable=False)
