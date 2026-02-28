from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class TournamentParticipant(Base):
    __tablename__ = "tournament_participants"
    __table_args__ = (
        CheckConstraint("score >= 0", name="ck_tournament_participants_score_non_negative"),
        CheckConstraint(
            "tie_break >= 0",
            name="ck_tournament_participants_tie_break_non_negative",
        ),
        Index(
            "idx_tournament_participants_tournament_score",
            "tournament_id",
            "score",
            "tie_break",
        ),
    )

    tournament_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tournaments.id"),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), primary_key=True)
    score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default=text("0"))
    tie_break: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, server_default=text("0")
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    standings_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    proof_card_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
