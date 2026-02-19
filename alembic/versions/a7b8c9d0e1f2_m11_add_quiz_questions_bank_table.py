"""m11_add_quiz_questions_bank_table

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-02-19 12:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quiz_questions",
        sa.Column("question_id", sa.String(length=64), nullable=False),
        sa.Column("mode_code", sa.String(length=32), nullable=False),
        sa.Column("source_file", sa.String(length=128), nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("option_1", sa.Text(), nullable=False),
        sa.Column("option_2", sa.Text(), nullable=False),
        sa.Column("option_3", sa.Text(), nullable=False),
        sa.Column("option_4", sa.Text(), nullable=False),
        sa.Column("correct_option_id", sa.SmallInteger(), nullable=False),
        sa.Column("correct_answer", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "correct_option_id >= 0 AND correct_option_id <= 3",
            name="ck_quiz_questions_correct_option_range",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','DISABLED')",
            name="ck_quiz_questions_status",
        ),
        sa.PrimaryKeyConstraint("question_id"),
    )
    op.create_index(
        "idx_quiz_questions_mode_status",
        "quiz_questions",
        ["mode_code", "status"],
    )
    op.create_index("idx_quiz_questions_level", "quiz_questions", ["level"])
    op.create_index("idx_quiz_questions_source_file", "quiz_questions", ["source_file"])


def downgrade() -> None:
    op.drop_index("idx_quiz_questions_source_file", table_name="quiz_questions")
    op.drop_index("idx_quiz_questions_level", table_name="quiz_questions")
    op.drop_index("idx_quiz_questions_mode_status", table_name="quiz_questions")
    op.drop_table("quiz_questions")
