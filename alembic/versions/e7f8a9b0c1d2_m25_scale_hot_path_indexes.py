"""m25_scale_hot_path_indexes

Revision ID: e7f8a9b0c1d2
Revises: c9d8e7f6a5b4
Create Date: 2026-02-24 18:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "c9d8e7f6a5b4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_purchases_paid_at_not_null",
        "purchases",
        ["paid_at"],
        unique=False,
        postgresql_where=sa.text("paid_at IS NOT NULL"),
        postgresql_include=["stars_amount", "product_code"],
    )
    op.create_index(
        "idx_purchases_user_product_paid_at",
        "purchases",
        ["user_id", "product_code", "paid_at"],
        unique=False,
        postgresql_where=sa.text("paid_at IS NOT NULL"),
    )
    op.create_index(
        "idx_quiz_questions_updated_at",
        "quiz_questions",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_quiz_questions_updated_at", table_name="quiz_questions")
    op.drop_index("idx_purchases_user_product_paid_at", table_name="purchases")
    op.drop_index("idx_purchases_paid_at_not_null", table_name="purchases")
