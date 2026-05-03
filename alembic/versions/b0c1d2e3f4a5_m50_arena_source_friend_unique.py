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
            WITH ranked_source_duels AS (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY source_friend_challenge_id
                        ORDER BY
                            CASE
                                WHEN status = 'ACTIVE' AND expires_at > now() THEN 0
                                ELSE 1
                            END,
                            created_at DESC,
                            id DESC
                    ) AS source_rank
                FROM arena_duels
                WHERE source_friend_challenge_id IS NOT NULL
            )
            UPDATE arena_duels
            SET
                source_friend_challenge_id = NULL,
                updated_at = now()
            FROM ranked_source_duels
            WHERE arena_duels.id = ranked_source_duels.id
              AND ranked_source_duels.source_rank > 1
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
