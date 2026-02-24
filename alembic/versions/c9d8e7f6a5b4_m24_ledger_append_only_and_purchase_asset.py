"""m24_ledger_append_only_and_purchase_asset

Revision ID: c9d8e7f6a5b4
Revises: b2c3d4e5f607
Create Date: 2026-02-24 10:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c9d8e7f6a5b4"
down_revision: str | None = "b2c3d4e5f607"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_ledger_entries_asset", "ledger_entries", type_="check")
    op.create_check_constraint(
        "ck_ledger_entries_asset",
        "ledger_entries",
        "asset IN ('FREE_ENERGY','PAID_ENERGY','PREMIUM','MODE_ACCESS','STREAK_SAVER','PURCHASE')",
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_ledger_entries_append_only()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'ledger_entries is append-only';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ledger_entries_append_only
        BEFORE UPDATE OR DELETE ON ledger_entries
        FOR EACH ROW
        EXECUTE FUNCTION fn_ledger_entries_append_only();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_ledger_entries_append_only ON ledger_entries;")
    op.execute("DROP FUNCTION IF EXISTS fn_ledger_entries_append_only();")

    op.drop_constraint("ck_ledger_entries_asset", "ledger_entries", type_="check")
    op.create_check_constraint(
        "ck_ledger_entries_asset",
        "ledger_entries",
        "asset IN ('FREE_ENERGY','PAID_ENERGY','PREMIUM','MODE_ACCESS','STREAK_SAVER')",
    )
