"""m56_reliability_base_tables

Revision ID: bd78ce90fa12
Revises: ac12bd34ef56
Create Date: 2026-07-15 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "bd78ce90fa12"
down_revision: str | None = "ac12bd34ef56"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_delivery_attempts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("flow", sa.String(length=64), nullable=False),
        sa.Column("task_name", sa.String(length=160), nullable=False),
        sa.Column("correlation_id", sa.String(length=160), nullable=False),
        sa.Column("idempotency_key", sa.String(length=220), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("chat_id_hash", sa.String(length=64), nullable=True),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("telegram_error_code", sa.Integer(), nullable=True),
        sa.Column("is_blocked_candidate", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "safe_context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("skipped_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('PENDING','SENT','FAILED','SKIPPED')",
            name="ck_telegram_delivery_attempts_status",
        ),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_telegram_delivery_attempts_idempotency_key"
        ),
    )

    op.create_table(
        "worker_task_heartbeats",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("task_name", sa.String(length=200), nullable=False),
        sa.Column("schedule_key", sa.String(length=160), nullable=False),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("last_error_hash", sa.String(length=64), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "task_name",
            "schedule_key",
            name="uq_worker_task_heartbeats_task_schedule",
        ),
    )

    op.create_table(
        "production_invariant_alerts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("severity", sa.String(length=8), nullable=False),
        sa.Column("type", sa.String(length=96), nullable=False),
        sa.Column("correlation_key", sa.String(length=180), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="OPEN"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "safe_context",
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
            "severity IN ('P0','P1','P2')",
            name="ck_production_invariant_alerts_severity",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','RESOLVED','ACKED')",
            name="ck_production_invariant_alerts_status",
        ),
        sa.UniqueConstraint(
            "type",
            "correlation_key",
            "status",
            name="uq_production_invariant_alerts_type_key_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("production_invariant_alerts")
    op.drop_table("worker_task_heartbeats")
    op.drop_table("telegram_delivery_attempts")
