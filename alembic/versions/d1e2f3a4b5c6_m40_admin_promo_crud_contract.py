"""m40_admin_promo_crud_contract

Revision ID: d1e2f3a4b5c6
Revises: c7d8e9f0a1b2
Create Date: 2026-03-08 14:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c7d8e9f0a1b2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("promo_codes", sa.Column("discount_type", sa.String(length=16), nullable=True))
    op.add_column("promo_codes", sa.Column("discount_value", sa.Integer(), nullable=True))
    op.add_column(
        "promo_codes",
        sa.Column("applicable_products", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.execute(
        """
        UPDATE promo_codes
        SET discount_type = CASE
                WHEN promo_type = 'PERCENT_DISCOUNT' THEN 'PERCENT'
                ELSE NULL
            END,
            discount_value = CASE
                WHEN promo_type = 'PERCENT_DISCOUNT' THEN discount_percent
                ELSE NULL
            END,
            applicable_products = CASE
                WHEN promo_type = 'PERCENT_DISCOUNT'
                    AND target_scope NOT IN ('ANY', 'MICRO_ANY', 'PREMIUM_ANY')
                THEN jsonb_build_array(target_scope)
                ELSE NULL
            END
        """
    )

    op.drop_constraint("ck_promo_codes_discount_percent", "promo_codes", type_="check")
    op.drop_constraint("ck_promo_codes_max_uses_per_user_is_one", "promo_codes", type_="check")
    op.drop_constraint("ck_promo_codes_type_payload_consistency", "promo_codes", type_="check")

    op.create_check_constraint(
        "ck_promo_codes_discount_percent",
        "promo_codes",
        "discount_percent IS NULL OR (discount_percent BETWEEN 1 AND 100)",
    )
    op.create_check_constraint(
        "ck_promo_codes_discount_type",
        "promo_codes",
        "discount_type IS NULL OR discount_type IN ('PERCENT','FIXED','FREE')",
    )
    op.create_check_constraint(
        "ck_promo_codes_max_uses_per_user_positive",
        "promo_codes",
        "max_uses_per_user > 0",
    )
    op.create_check_constraint(
        "ck_promo_codes_type_payload_consistency",
        "promo_codes",
        "((promo_type = 'PREMIUM_GRANT' AND grant_premium_days IS NOT NULL AND discount_percent IS NULL "
        "AND discount_type IS NULL AND discount_value IS NULL) "
        "OR (promo_type = 'PERCENT_DISCOUNT' AND grant_premium_days IS NULL "
        "AND ((discount_type IS NULL AND discount_percent IS NOT NULL) "
        "OR (discount_type = 'PERCENT' AND discount_value IS NOT NULL AND discount_value BETWEEN 1 AND 100) "
        "OR (discount_type = 'FIXED' AND discount_value IS NOT NULL AND discount_value > 0) "
        "OR (discount_type = 'FREE' AND discount_value IS NULL))))",
    )

    op.drop_constraint("uq_promo_redemptions_code_user", "promo_redemptions", type_="unique")

    op.drop_constraint("ck_purchases_stars_amount_positive", "purchases", type_="check")
    op.drop_constraint("ck_purchases_final_amount", "purchases", type_="check")
    op.create_check_constraint(
        "ck_purchases_stars_amount_non_negative",
        "purchases",
        "stars_amount >= 0",
    )
    op.create_check_constraint(
        "ck_purchases_final_amount",
        "purchases",
        "stars_amount = GREATEST(0, base_stars_amount - discount_stars_amount)",
    )

    op.create_table(
        "promo_audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("admin_email", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("promo_code_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["promo_code_id"], ["promo_codes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_promo_audit_log_created_at", "promo_audit_log", ["created_at"])
    op.create_index(
        "idx_promo_audit_log_action",
        "promo_audit_log",
        ["action", "created_at"],
    )
    op.create_index(
        "idx_promo_audit_log_promo_created_at",
        "promo_audit_log",
        ["promo_code_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_promo_audit_log_promo_created_at", table_name="promo_audit_log")
    op.drop_index("idx_promo_audit_log_action", table_name="promo_audit_log")
    op.drop_index("idx_promo_audit_log_created_at", table_name="promo_audit_log")
    op.drop_table("promo_audit_log")

    op.drop_constraint("ck_purchases_final_amount", "purchases", type_="check")
    op.drop_constraint("ck_purchases_stars_amount_non_negative", "purchases", type_="check")
    op.create_check_constraint(
        "ck_purchases_stars_amount_positive",
        "purchases",
        "stars_amount > 0",
    )
    op.create_check_constraint(
        "ck_purchases_final_amount",
        "purchases",
        "stars_amount = GREATEST(1, base_stars_amount - discount_stars_amount)",
    )

    op.create_unique_constraint(
        "uq_promo_redemptions_code_user",
        "promo_redemptions",
        ["promo_code_id", "user_id"],
    )

    op.drop_constraint("ck_promo_codes_type_payload_consistency", "promo_codes", type_="check")
    op.drop_constraint("ck_promo_codes_max_uses_per_user_positive", "promo_codes", type_="check")
    op.drop_constraint("ck_promo_codes_discount_type", "promo_codes", type_="check")
    op.drop_constraint("ck_promo_codes_discount_percent", "promo_codes", type_="check")

    op.create_check_constraint(
        "ck_promo_codes_discount_percent",
        "promo_codes",
        "discount_percent IS NULL OR (discount_percent BETWEEN 1 AND 90)",
    )
    op.create_check_constraint(
        "ck_promo_codes_max_uses_per_user_is_one",
        "promo_codes",
        "max_uses_per_user = 1",
    )
    op.create_check_constraint(
        "ck_promo_codes_type_payload_consistency",
        "promo_codes",
        "((promo_type = 'PREMIUM_GRANT' AND grant_premium_days IS NOT NULL AND discount_percent IS NULL) "
        "OR (promo_type = 'PERCENT_DISCOUNT' AND discount_percent IS NOT NULL AND grant_premium_days IS NULL))",
    )

    op.drop_column("promo_codes", "applicable_products")
    op.drop_column("promo_codes", "discount_value")
    op.drop_column("promo_codes", "discount_type")
