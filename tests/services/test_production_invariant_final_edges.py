from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from app.services.production_invariant_checks.delivery_daily import build_daily_cup_delivery_checks
from app.services.production_invariant_checks.freshness import build_freshness_checks
from app.services.production_invariant_checks.heartbeat import build_heartbeat_checks
from app.workers.task_heartbeat import CriticalTaskHeartbeat, get_critical_task_heartbeats

NOW_UTC = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)


def test_reliability_migration_seeds_persistent_heartbeat_grace_baseline() -> None:
    migration = Path(
        "alembic/versions/b6c7d8e9f012_m56_production_reliability_foundation.py"
    ).read_text()

    assert "INSERT INTO worker_task_heartbeats" in migration
    assert "__production_reliability_migration_baseline__" in migration


def test_missing_heartbeat_is_graceful_immediately_after_migration() -> None:
    count = _heartbeat_count(_heartbeat_baseline_row(NOW_UTC))

    assert count == 0


def test_missing_heartbeat_after_grace_window_is_stale() -> None:
    count = _heartbeat_count(_heartbeat_baseline_row(NOW_UTC - timedelta(minutes=3)))

    assert count == 1


def test_existing_stale_heartbeat_row_is_stale() -> None:
    count = _heartbeat_count(
        """
        INSERT INTO worker_task_heartbeats VALUES (
            'task', 'schedule', '2026-07-12 11:57:00+00:00', 0
        );
        """,
    )

    assert count == 1


def test_fresh_success_heartbeat_row_is_ok() -> None:
    count = _heartbeat_count(
        """
        INSERT INTO worker_task_heartbeats VALUES (
            'task', 'schedule', '2026-07-12 11:59:30+00:00', 0
        );
        """,
    )

    assert count == 0


def test_consecutive_heartbeat_failures_are_stale_even_with_fresh_success() -> None:
    count = _heartbeat_count(
        """
        INSERT INTO worker_task_heartbeats VALUES (
            'task', 'schedule', '2026-07-12 11:59:30+00:00', 2
        );
        """,
    )

    assert count == 1


def test_disabled_premium_expiry_does_not_create_stale_heartbeat_check() -> None:
    checks = build_heartbeat_checks(
        NOW_UTC,
        get_critical_task_heartbeats(premium_expiry_schedule_enabled=False),
    )

    schedule_keys = {check.safe_context["schedule_key"] for check in checks}

    assert "premium-expiry-lifecycle-hourly" not in schedule_keys


def test_enabled_premium_expiry_missing_after_grace_is_stale() -> None:
    premium_row = next(
        row
        for row in get_critical_task_heartbeats(premium_expiry_schedule_enabled=True)
        if row.schedule_key == "premium-expiry-lifecycle-hourly"
    )
    check = build_heartbeat_checks(
        NOW_UTC,
        (premium_row,),
    )[0]

    assert (
        _run_invariant_sql(
            check.sql,
            check.params,
            _heartbeat_table_sql() + _heartbeat_baseline_row(NOW_UTC - timedelta(hours=3)),
        )
        == 1
    )


def test_stale_pending_non_offer_delivery_is_detected_globally() -> None:
    assert (
        _telegram_pending_count(
            """
        INSERT INTO telegram_delivery_attempts VALUES (
            'arena_beaten_notification', 'PENDING', '2026-07-12 11:00:00+00:00'
        );
        """
        )
        == 1
    )


def test_fresh_or_terminal_delivery_attempts_are_not_stale_pending() -> None:
    assert (
        _telegram_pending_count(
            """
        INSERT INTO telegram_delivery_attempts VALUES
            ('daily_cup_registration_push', 'PENDING', '2026-07-12 11:50:00+00:00'),
            ('daily_cup_cancel_message', 'SENT', '2026-07-12 11:00:00+00:00'),
            ('daily_cup_turn_reminder', 'FAILED', '2026-07-12 11:00:00+00:00');
        """
        )
        == 0
    )


def test_old_manual_review_open_outbox_row_is_not_queue_stale() -> None:
    count = _freshness_queue_count(
        """
        INSERT INTO outbox_events VALUES (
            'payments_telegram_stars_reconciliation_review',
            'OPEN',
            '2026-07-12 11:00:00+00:00'
        );
        """
    )

    assert count == 0


def test_old_retryable_queue_row_is_stale() -> None:
    count = _freshness_queue_count(
        """
        INSERT INTO outbox_events VALUES (
            'telegram_update_delivery', 'RETRY', '2026-07-12 11:00:00+00:00'
        );
        """
    )

    assert count == 1


def test_mixed_manual_review_and_real_stuck_queue_counts_real_row_only() -> None:
    count = _freshness_queue_count(
        """
        INSERT INTO outbox_events VALUES (
            'payments_telegram_stars_reconciliation_review',
            'OPEN',
            '2026-07-12 11:00:00+00:00'
        );
        INSERT INTO outbox_events VALUES (
            'telegram_update_delivery', 'PENDING', '2026-07-12 11:00:00+00:00'
        );
        """
    )

    assert count == 1


def test_empty_outbox_queue_is_ok() -> None:
    assert _freshness_queue_count("") == 0


def test_canceled_daily_cup_without_cancel_outcome_is_finding() -> None:
    count = _daily_cancel_count(
        """
        INSERT INTO tournaments VALUES (
            'cup-1', 'DAILY_ARENA', 'CANCELED', 0, '2026-07-12 11:00:00+00:00'
        );
        INSERT INTO users VALUES (1, 1001, 'ACTIVE');
        INSERT INTO tournament_participants VALUES ('cup-1', 1);
        """
    )

    assert count == 1


def test_canceled_daily_cup_with_cancel_outcome_is_ok() -> None:
    count = _daily_cancel_count(
        """
        INSERT INTO tournaments VALUES (
            'cup-1', 'DAILY_ARENA', 'CANCELED', 0, '2026-07-12 11:00:00+00:00'
        );
        INSERT INTO users VALUES (1, 1001, 'ACTIVE');
        INSERT INTO tournament_participants VALUES ('cup-1', 1);
        INSERT INTO telegram_delivery_attempts VALUES (
            'daily_cup_cancel_message', 'cup-1', 1001, 'SENT'
        );
        """
    )

    assert count == 0


def test_canceled_daily_cup_without_active_targets_is_ok() -> None:
    count = _daily_cancel_count(
        """
        INSERT INTO tournaments VALUES (
            'cup-1', 'DAILY_ARENA', 'CANCELED', 0, '2026-07-12 11:00:00+00:00'
        );
        INSERT INTO users VALUES (1, 1001, 'BLOCKED');
        INSERT INTO tournament_participants VALUES ('cup-1', 1);
        """
    )

    assert count == 0


def test_canceled_daily_cup_still_does_not_require_round_outcomes() -> None:
    check = next(
        check
        for check in build_daily_cup_delivery_checks(NOW_UTC - timedelta(days=2))
        if check.name == "daily_cup_round_delivery_gap"
    )
    count = _run_invariant_sql(
        check.sql,
        check.params,
        """
        CREATE TABLE tournaments (
            id TEXT, type TEXT, status TEXT, current_round INTEGER, created_at TEXT
        );
        CREATE TABLE tournament_participants (tournament_id TEXT, user_id INTEGER);
        CREATE TABLE users (id INTEGER, status TEXT, telegram_user_id INTEGER);
        CREATE TABLE telegram_delivery_attempts (
            flow TEXT, correlation_id TEXT, target_id TEXT, status TEXT
        );
        INSERT INTO tournaments VALUES (
            'cup-1', 'DAILY_ARENA', 'CANCELED', 0, '2026-07-12 11:00:00+00:00'
        );
        INSERT INTO users VALUES (1, 'ACTIVE', 1001);
        INSERT INTO tournament_participants VALUES ('cup-1', 1);
        """,
    )

    assert count == 0


def _heartbeat_count(rows_sql: str) -> int:
    check = build_heartbeat_checks(
        NOW_UTC,
        (
            CriticalTaskHeartbeat(
                task_name="task",
                schedule_key="schedule",
                stale_after_seconds=120,
            ),
        ),
    )[0]
    return _run_invariant_sql(
        check.sql,
        check.params,
        _heartbeat_table_sql() + rows_sql,
    )


def _freshness_queue_count(rows_sql: str) -> int:
    check = next(
        check
        for check in build_freshness_checks(NOW_UTC, date(2026, 7, 12))
        if check.name == "queue_oldest_message_age_seconds"
    )
    return _run_invariant_sql(
        check.sql,
        check.params,
        "CREATE TABLE outbox_events (event_type TEXT, status TEXT, created_at TEXT);" + rows_sql,
    )


def _heartbeat_baseline_row(baseline_at: datetime) -> str:
    return f"""
        INSERT INTO worker_task_heartbeats VALUES (
            '__system__', '__production_reliability_migration_baseline__',
            '{baseline_at.isoformat(sep=" ")}', 0
        );
    """


def _telegram_pending_count(rows_sql: str) -> int:
    check = next(
        check
        for check in build_freshness_checks(NOW_UTC, date(2026, 7, 12))
        if check.name == "telegram_delivery_pending_stale"
    )
    return _run_invariant_sql(
        check.sql,
        check.params,
        "CREATE TABLE telegram_delivery_attempts (flow TEXT, status TEXT, updated_at TEXT);"
        + rows_sql,
    )


def _daily_cancel_count(rows_sql: str) -> int:
    check = next(
        check
        for check in build_daily_cup_delivery_checks(NOW_UTC - timedelta(days=2))
        if check.name == "daily_cup_cancel_message_gap"
    )
    return _run_invariant_sql(
        check.sql,
        check.params,
        """
        CREATE TABLE tournaments (
            id TEXT, type TEXT, status TEXT, current_round INTEGER, created_at TEXT
        );
        CREATE TABLE tournament_participants (tournament_id TEXT, user_id INTEGER);
        CREATE TABLE users (id INTEGER, telegram_user_id INTEGER, status TEXT);
        CREATE TABLE telegram_delivery_attempts (
            flow TEXT, correlation_id TEXT, telegram_user_id INTEGER, status TEXT
        );
        """
        + rows_sql,
    )


def _run_invariant_sql(sql: str, params: dict[str, object], setup_sql: str) -> int:
    translated_sql = sql.replace("::text", "").replace("GREATEST(", "max(")
    translated_params = {
        key: value.isoformat(sep=" ") if isinstance(value, datetime) else value
        for key, value in params.items()
    }
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(setup_sql)
        row = connection.execute(translated_sql, translated_params).fetchone()
    finally:
        connection.close()
    assert row is not None
    return int(row[0] or 0)


def _heartbeat_table_sql() -> str:
    return """
        CREATE TABLE worker_task_heartbeats (
            task_name TEXT,
            schedule_key TEXT,
            last_success_at TEXT,
            consecutive_failures INTEGER
        );
        """
