"""m7_add_question_id_to_quiz_sessions

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-02-18 12:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("quiz_sessions", sa.Column("question_id", sa.String(length=64), nullable=True))
    op.create_index("idx_sessions_question", "quiz_sessions", ["question_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_sessions_question", table_name="quiz_sessions")
    op.drop_column("quiz_sessions", "question_id")
