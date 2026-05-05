"""m52_add_duel_funnel_daily_metrics

Revision ID: d6e7f8a9b0c2
Revises: c0d1e2f3a4b5
Create Date: 2026-05-05 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d6e7f8a9b0c2"
down_revision: str | None = "c0d1e2f3a4b5"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

DUEL_DAILY_METRIC_COLUMNS = (
    ("duel_menu_opened_events_total", "ck_analytics_daily_duel_menu_opened_non_negative"),
    ("duel_mode_selected_events_total", "ck_analytics_daily_duel_mode_selected_non_negative"),
    ("arena_opened_events_total", "ck_analytics_daily_arena_opened_non_negative"),
    ("arena_duel_created_events_total", "ck_analytics_daily_arena_duel_created_non_negative"),
    ("arena_duel_started_events_total", "ck_analytics_daily_arena_duel_started_non_negative"),
    (
        "arena_duel_completed_events_total",
        "ck_analytics_daily_arena_duel_completed_non_negative",
    ),
    (
        "arena_duel_published_events_total",
        "ck_analytics_daily_arena_duel_published_non_negative",
    ),
    ("arena_duel_accepted_events_total", "ck_analytics_daily_arena_duel_accepted_non_negative"),
    ("arena_result_shown_events_total", "ck_analytics_daily_arena_result_shown_non_negative"),
    (
        "arena_result_beaten_notification_sent_events_total",
        "ck_analytics_daily_arena_beaten_notice_non_negative",
    ),
    (
        "arena_revanche_clicked_events_total",
        "ck_analytics_daily_arena_revanche_clicked_non_negative",
    ),
    ("friend_duel_opened_events_total", "ck_analytics_daily_friend_duel_opened_non_negative"),
    ("friend_duel_created_events_total", "ck_analytics_daily_friend_duel_created_non_negative"),
    (
        "friend_duel_share_clicked_events_total",
        "ck_analytics_daily_friend_share_clicked_non_negative",
    ),
    ("friend_duel_joined_events_total", "ck_analytics_daily_friend_duel_joined_non_negative"),
    ("friend_duel_started_events_total", "ck_analytics_daily_friend_duel_started_non_negative"),
    (
        "friend_duel_completed_events_total",
        "ck_analytics_daily_friend_duel_completed_non_negative",
    ),
    (
        "friend_duel_published_to_arena_events_total",
        "ck_analytics_daily_friend_publish_arena_non_negative",
    ),
    (
        "friend_duel_revanche_clicked_events_total",
        "ck_analytics_daily_friend_revanche_clicked_non_negative",
    ),
    ("duel_limit_hit_events_total", "ck_analytics_daily_duel_limit_hit_non_negative"),
    ("duel_paywall_shown_events_total", "ck_analytics_daily_duel_paywall_shown_non_negative"),
    ("duel_ticket_clicked_events_total", "ck_analytics_daily_duel_ticket_clicked_non_negative"),
    ("premium_week_clicked_events_total", "ck_analytics_daily_premium_week_clicked_non_negative"),
)


def upgrade() -> None:
    for column_name, _constraint_name in DUEL_DAILY_METRIC_COLUMNS:
        op.add_column(
            "analytics_daily",
            sa.Column(column_name, sa.Integer(), nullable=False, server_default=sa.text("0")),
        )

    for column_name, constraint_name in DUEL_DAILY_METRIC_COLUMNS:
        op.create_check_constraint(
            constraint_name,
            "analytics_daily",
            f"{column_name} >= 0",
        )


def downgrade() -> None:
    for _column_name, constraint_name in reversed(DUEL_DAILY_METRIC_COLUMNS):
        op.drop_constraint(constraint_name, "analytics_daily", type_="check")

    for column_name, _constraint_name in reversed(DUEL_DAILY_METRIC_COLUMNS):
        op.drop_column("analytics_daily", column_name)
