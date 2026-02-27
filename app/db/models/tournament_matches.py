from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class TournamentMatch(Base):
    __tablename__ = "tournament_matches"
    __table_args__ = (
        CheckConstraint(
            "round_no >= 1 AND round_no <= 3",
            name="ck_tournament_matches_round_no_range",
        ),
        CheckConstraint(
            "status IN ('PENDING','COMPLETED','WALKOVER')",
            name="ck_tournament_matches_status",
        ),
        CheckConstraint(
            "user_b IS NULL OR user_a <> user_b",
            name="ck_tournament_matches_no_self_pair",
        ),
        Index(
            "idx_tournament_matches_tournament_round_status",
            "tournament_id",
            "round_no",
            "status",
        ),
        Index(
            "idx_tournament_matches_tournament_status_deadline",
            "tournament_id",
            "status",
            "deadline",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tournament_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tournaments.id"), nullable=False
    )
    round_no: Mapped[int] = mapped_column(Integer, nullable=False)
    user_a: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    user_b: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    friend_challenge_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("friend_challenges.id"),
        unique=True,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    winner_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
