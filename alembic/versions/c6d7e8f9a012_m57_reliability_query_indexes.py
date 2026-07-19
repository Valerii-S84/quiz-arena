"""m57_reliability_query_indexes

Revision ID: c6d7e8f9a012
Revises: bd78ce90fa12
Create Date: 2026-07-16 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c6d7e8f9a012"
down_revision: str | None = "bd78ce90fa12"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_telegram_delivery_flow_correlation",
        "telegram_delivery_attempts",
        ["flow", "correlation_id", "status"],
    )
    op.create_index(
        "idx_telegram_delivery_target",
        "telegram_delivery_attempts",
        ["target_type", "target_id", "created_at"],
    )
    op.create_index(
        "idx_telegram_delivery_blocked_candidate",
        "telegram_delivery_attempts",
        ["is_blocked_candidate", "created_at"],
    )
    op.create_index(
        "idx_worker_task_heartbeats_success",
        "worker_task_heartbeats",
        ["last_success_at"],
    )
    op.create_index(
        "idx_worker_task_heartbeats_failure",
        "worker_task_heartbeats",
        ["last_failed_at"],
    )
    op.create_index(
        "idx_production_invariant_alerts_status_seen",
        "production_invariant_alerts",
        ["status", "last_seen_at"],
    )
    op.create_index(
        "idx_production_invariant_alerts_type_seen",
        "production_invariant_alerts",
        ["type", "last_seen_at"],
    )
    op.create_index(
        "uq_production_invariant_alerts_active_type_key",
        "production_invariant_alerts",
        ["type", "correlation_key"],
        unique=True,
        postgresql_where=sa.text("status = 'OPEN'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_production_invariant_alerts_active_type_key",
        table_name="production_invariant_alerts",
    )
    op.drop_index(
        "idx_production_invariant_alerts_type_seen", table_name="production_invariant_alerts"
    )
    op.drop_index(
        "idx_production_invariant_alerts_status_seen", table_name="production_invariant_alerts"
    )
    op.drop_index("idx_worker_task_heartbeats_failure", table_name="worker_task_heartbeats")
    op.drop_index("idx_worker_task_heartbeats_success", table_name="worker_task_heartbeats")
    op.drop_index(
        "idx_telegram_delivery_blocked_candidate", table_name="telegram_delivery_attempts"
    )
    op.drop_index("idx_telegram_delivery_target", table_name="telegram_delivery_attempts")
    op.drop_index("idx_telegram_delivery_flow_correlation", table_name="telegram_delivery_attempts")
