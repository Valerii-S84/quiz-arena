"""m35_contact_requests_inbox

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-03-04 13:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contact_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("request_type", sa.String(16), nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'NEW'"),
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("contact", sa.String(200), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
            "request_type IN ('student','partner')",
            name="ck_contact_requests_type",
        ),
        sa.CheckConstraint(
            "status IN ('NEW','IN_PROGRESS','DONE','SPAM')",
            name="ck_contact_requests_status",
        ),
    )
    op.create_index("idx_contact_requests_created_at", "contact_requests", ["created_at"])
    op.create_index(
        "idx_contact_requests_type_created",
        "contact_requests",
        ["request_type", "created_at"],
    )
    op.create_index(
        "idx_contact_requests_status_created",
        "contact_requests",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_contact_requests_status_created", table_name="contact_requests")
    op.drop_index("idx_contact_requests_type_created", table_name="contact_requests")
    op.drop_index("idx_contact_requests_created_at", table_name="contact_requests")
    op.drop_table("contact_requests")
