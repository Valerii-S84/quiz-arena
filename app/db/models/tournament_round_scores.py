from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class TournamentRoundScore(Base):
    __tablename__ = "tournament_round_scores"
    __table_args__ = (
        CheckConstraint(
            "round_number >= 1 AND round_number <= 4", name="ck_round_scores_round_range"
        ),
        CheckConstraint("wins IN (0, 1, 2)", name="ck_round_scores_points_range"),
        CheckConstraint(
            "correct_answers >= 0 AND correct_answers <= 7",
            name="ck_round_scores_correct_answers_range",
        ),
        CheckConstraint("total_time_ms >= 0", name="ck_round_scores_total_time_non_negative"),
        Index(
            "uq_round_scores_tournament_round_player",
            "tournament_id",
            "round_number",
            "player_id",
            unique=True,
        ),
        Index(
            "idx_round_scores_tournament_player",
            "tournament_id",
            "player_id",
            "round_number",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tournament_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tournaments.id"), nullable=False
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    opponent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    wins: Mapped[int] = mapped_column(Integer, nullable=False)
    is_draw: Mapped[bool] = mapped_column(Boolean, nullable=False)
    correct_answers: Mapped[int] = mapped_column(Integer, nullable=False)
    total_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    got_bye: Mapped[bool] = mapped_column(Boolean, nullable=False)
    auto_finished: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
