from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"
    __table_args__ = (
        CheckConstraint(
            "correct_option_id >= 0 AND correct_option_id <= 3",
            name="ck_quiz_questions_correct_option_range",
        ),
        CheckConstraint(
            "status IN ('ACTIVE','DISABLED')",
            name="ck_quiz_questions_status",
        ),
        Index("idx_quiz_questions_mode_status", "mode_code", "status"),
        Index("idx_quiz_questions_level", "level"),
        Index("idx_quiz_questions_source_file", "source_file"),
    )

    question_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mode_code: Mapped[str] = mapped_column(String(32), nullable=False)
    source_file: Mapped[str] = mapped_column(String(128), nullable=False)
    level: Mapped[str] = mapped_column(String(8), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    option_1: Mapped[str] = mapped_column(Text, nullable=False)
    option_2: Mapped[str] = mapped_column(Text, nullable=False)
    option_3: Mapped[str] = mapped_column(Text, nullable=False)
    option_4: Mapped[str] = mapped_column(Text, nullable=False)
    correct_option_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    correct_answer: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
