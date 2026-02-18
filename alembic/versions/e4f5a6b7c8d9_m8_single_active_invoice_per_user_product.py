"""m8_single_active_invoice_per_user_product

Revision ID: e4f5a6b7c8d9
Revises: d2e3f4a5b6c7
Create Date: 2026-02-18 16:35:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "d2e3f4a5b6c7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_purchases_active_invoice_user_product",
        "purchases",
        ["user_id", "product_code"],
        unique=True,
        postgresql_where=sa.text("status IN ('CREATED','INVOICE_SENT','PRECHECKOUT_OK')"),
    )


def downgrade() -> None:
    op.drop_index("uq_purchases_active_invoice_user_product", table_name="purchases")
