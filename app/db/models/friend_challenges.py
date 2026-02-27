from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class FriendChallenge(Base):
    __tablename__ = "friend_challenges"
    __table_args__ = (
        CheckConstraint(
            (
                "status IN ("
                "'ACTIVE','PENDING','ACCEPTED','CREATOR_DONE','OPPONENT_DONE',"
                "'COMPLETED','EXPIRED','CANCELED','WALKOVER'"
                ")"
            ),
            name="ck_friend_challenges_status",
        ),
        CheckConstraint(
            "challenge_type IN ('DIRECT','OPEN')",
            name="ck_friend_challenges_challenge_type",
        ),
        CheckConstraint(
            "access_type IN ('FREE','PAID_TICKET','PREMIUM')",
            name="ck_friend_challenges_access_type",
        ),
        CheckConstraint("current_round >= 1", name="ck_friend_challenges_current_round_positive"),
        CheckConstraint("total_rounds >= 1", name="ck_friend_challenges_total_rounds_positive"),
        CheckConstraint(
            "series_game_number >= 1", name="ck_friend_challenges_series_game_positive"
        ),
        CheckConstraint("series_best_of >= 1", name="ck_friend_challenges_series_best_of_positive"),
        CheckConstraint(
            "creator_score >= 0", name="ck_friend_challenges_creator_score_non_negative"
        ),
        CheckConstraint(
            "opponent_score >= 0",
            name="ck_friend_challenges_opponent_score_non_negative",
        ),
        CheckConstraint(
            "creator_answered_round >= 0",
            name="ck_friend_challenges_creator_answered_non_negative",
        ),
        CheckConstraint(
            "opponent_answered_round >= 0",
            name="ck_friend_challenges_opponent_answered_non_negative",
        ),
        Index("idx_friend_challenges_creator_created", "creator_user_id", "created_at"),
        Index("idx_friend_challenges_opponent_created", "opponent_user_id", "created_at"),
        Index("idx_friend_challenges_status_created", "status", "created_at"),
        Index("idx_friend_challenges_status_expires", "status", "expires_at"),
        Index("idx_friend_challenges_series_game", "series_id", "series_game_number"),
        Index("idx_friend_challenges_type_status", "challenge_type", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    invite_token: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    creator_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    opponent_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    challenge_type: Mapped[str] = mapped_column(String(16), nullable=False)
    mode_code: Mapped[str] = mapped_column(String(32), nullable=False)
    access_type: Mapped[str] = mapped_column(String(16), nullable=False)
    question_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    tournament_match_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    current_round: Mapped[int] = mapped_column(Integer, nullable=False)
    total_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    series_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    series_game_number: Mapped[int] = mapped_column(Integer, nullable=False)
    series_best_of: Mapped[int] = mapped_column(Integer, nullable=False)
    creator_score: Mapped[int] = mapped_column(Integer, nullable=False)
    opponent_score: Mapped[int] = mapped_column(Integer, nullable=False)
    creator_answered_round: Mapped[int] = mapped_column(Integer, nullable=False)
    opponent_answered_round: Mapped[int] = mapped_column(Integer, nullable=False)
    winner_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    creator_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    opponent_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    creator_push_count: Mapped[int] = mapped_column(Integer, nullable=False)
    opponent_push_count: Mapped[int] = mapped_column(Integer, nullable=False)
    creator_proof_card_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    opponent_proof_card_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_last_chance_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
