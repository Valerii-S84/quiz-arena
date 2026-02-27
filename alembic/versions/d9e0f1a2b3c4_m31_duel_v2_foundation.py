"""m31_duel_v2_foundation

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-02-27 23:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d9e0f1a2b3c4"
down_revision: str | None = "c8d9e0f1a2b3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "friend_challenges",
        sa.Column("challenge_type", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "friend_challenges",
        sa.Column("question_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "friend_challenges",
        sa.Column("tournament_match_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "friend_challenges",
        sa.Column("creator_finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "friend_challenges",
        sa.Column("opponent_finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "friend_challenges",
        sa.Column("creator_push_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "friend_challenges",
        sa.Column("opponent_push_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "friend_challenges",
        sa.Column("creator_proof_card_file_id", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "friend_challenges",
        sa.Column("opponent_proof_card_file_id", sa.String(length=256), nullable=True),
    )

    op.create_index(
        "idx_friend_challenges_type_status",
        "friend_challenges",
        ["challenge_type", "status", "created_at"],
    )
    op.create_check_constraint(
        "ck_friend_challenges_challenge_type",
        "friend_challenges",
        "challenge_type IN ('DIRECT','OPEN')",
    )

    op.execute("UPDATE friend_challenges SET challenge_type = 'DIRECT' WHERE challenge_type IS NULL")

    op.execute(
        """
        UPDATE friend_challenges
        SET creator_finished_at = COALESCE(completed_at, updated_at, created_at)
        WHERE creator_finished_at IS NULL
          AND creator_answered_round >= total_rounds
        """
    )
    op.execute(
        """
        UPDATE friend_challenges
        SET opponent_finished_at = COALESCE(completed_at, updated_at, created_at)
        WHERE opponent_finished_at IS NULL
          AND opponent_answered_round >= total_rounds
        """
    )

    # Old status check allows only ACTIVE/COMPLETED/CANCELED/EXPIRED.
    # Drop it before remapping ACTIVE -> new duel statuses.
    op.drop_constraint("ck_friend_challenges_status", "friend_challenges", type_="check")

    op.execute(
        """
        UPDATE friend_challenges
        SET status = 'PENDING'
        WHERE status = 'ACTIVE'
          AND opponent_user_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE friend_challenges
        SET status = 'COMPLETED'
        WHERE status = 'ACTIVE'
          AND opponent_user_id IS NOT NULL
          AND creator_answered_round >= total_rounds
          AND opponent_answered_round >= total_rounds
        """
    )
    op.execute(
        """
        UPDATE friend_challenges
        SET status = 'CREATOR_DONE'
        WHERE status = 'ACTIVE'
          AND opponent_user_id IS NOT NULL
          AND creator_answered_round >= total_rounds
          AND opponent_answered_round < total_rounds
        """
    )
    op.execute(
        """
        UPDATE friend_challenges
        SET status = 'OPPONENT_DONE'
        WHERE status = 'ACTIVE'
          AND opponent_user_id IS NOT NULL
          AND opponent_answered_round >= total_rounds
          AND creator_answered_round < total_rounds
        """
    )
    op.execute(
        """
        UPDATE friend_challenges
        SET status = 'ACCEPTED'
        WHERE status = 'ACTIVE'
          AND opponent_user_id IS NOT NULL
        """
    )

    op.alter_column("friend_challenges", "challenge_type", nullable=False)
    op.alter_column("friend_challenges", "creator_push_count", server_default=None)
    op.alter_column("friend_challenges", "opponent_push_count", server_default=None)

    op.create_check_constraint(
        "ck_friend_challenges_status",
        "friend_challenges",
        (
            "status IN ("
            "'ACTIVE','PENDING','ACCEPTED','CREATOR_DONE','OPPONENT_DONE',"
            "'COMPLETED','EXPIRED','CANCELED','WALKOVER'"
            ")"
        ),
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE friend_challenges
        SET status = 'ACTIVE'
        WHERE status IN ('PENDING','ACCEPTED','CREATOR_DONE','OPPONENT_DONE')
        """
    )
    op.execute(
        """
        UPDATE friend_challenges
        SET status = 'EXPIRED'
        WHERE status = 'WALKOVER'
        """
    )

    op.drop_constraint("ck_friend_challenges_status", "friend_challenges", type_="check")
    op.create_check_constraint(
        "ck_friend_challenges_status",
        "friend_challenges",
        "status IN ('ACTIVE','COMPLETED','CANCELED','EXPIRED')",
    )

    op.drop_constraint("ck_friend_challenges_challenge_type", "friend_challenges", type_="check")
    op.drop_index("idx_friend_challenges_type_status", table_name="friend_challenges")

    op.drop_column("friend_challenges", "opponent_proof_card_file_id")
    op.drop_column("friend_challenges", "creator_proof_card_file_id")
    op.drop_column("friend_challenges", "opponent_push_count")
    op.drop_column("friend_challenges", "creator_push_count")
    op.drop_column("friend_challenges", "opponent_finished_at")
    op.drop_column("friend_challenges", "creator_finished_at")
    op.drop_column("friend_challenges", "tournament_match_id")
    op.drop_column("friend_challenges", "question_ids")
    op.drop_column("friend_challenges", "challenge_type")
