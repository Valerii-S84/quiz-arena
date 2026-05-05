"""m50_arena_source_friend_unique

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-05-03 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b0c1d2e3f4a5"
down_revision: str | None = "a9b0c1d2e3f4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM arena_duels
                    WHERE source_friend_challenge_id IS NOT NULL
                    GROUP BY source_friend_challenge_id
                    HAVING COUNT(*) > 1
                ) THEN
                    RAISE EXCEPTION
                        'Cannot enforce uq_arena_duels_source_friend_once: duplicate source_friend_challenge_id rows exist'
                        USING HINT = 'Resolve duplicates with an approved maintenance flow before rerunning m50_arena_source_friend_unique.';
                END IF;
            END
            $$;
            """
        )
    )
    op.create_index(
        "uq_arena_duels_source_friend_once",
        "arena_duels",
        ["source_friend_challenge_id"],
        unique=True,
        postgresql_where=sa.text("source_friend_challenge_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_arena_duels_source_friend_once", table_name="arena_duels")
