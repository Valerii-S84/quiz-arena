from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from app.services.production_invariants import InvariantCheck, build_invariant_checks

NOW_UTC = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def test_private_tournament_delivery_gap_is_current_phase_specific() -> None:
    check = _check_by_name("private_tournament_round_delivery_gap")

    assert "p.user_id::text || ':phase:'" in check.sql
    assert "WHEN t.status = 'COMPLETED' THEN 'status:completed'" in check.sql
    assert "'round:' || GREATEST(1, t.current_round)::text" in check.sql
    assert "':status:' || lower(t.status)" in check.sql
    assert "t.status IN ('ROUND_1','ROUND_2','ROUND_3','ROUND_4','BRACKET_LIVE')" in check.sql
    assert "FROM tournament_matches m" in check.sql
    assert "FROM worker_task_heartbeats" in check.sql
    assert "t.created_at >= b.started_at" in check.sql


def test_private_tournament_gap_counts_missing_current_phase_participant() -> None:
    check = _check_by_name("private_tournament_round_delivery_gap")
    count = _run_invariant_sql(
        check.sql,
        check.params,
        _private_schema()
        + """
        INSERT INTO tournaments VALUES (
            't-1', 'PRIVATE', 'ROUND_2', 2, '2026-07-10 18:00:00+00:00',
            '2026-07-10 11:00:00+00:00'
        );
        INSERT INTO tournament_participants VALUES ('t-1', 1), ('t-1', 2);
        INSERT INTO telegram_delivery_attempts VALUES (
            'private_tournament_round_messaging', 't-1',
            '1:phase:round:2:status:round_2:edit:101', 'SENT'
        );
        INSERT INTO telegram_delivery_attempts VALUES (
            'private_tournament_round_messaging', 't-1',
            '2:phase:round:1:status:round_1:edit:202', 'SENT'
        );
        """,
    )

    assert count == 1


def test_private_tournament_gap_includes_long_running_active_round() -> None:
    check = _check_by_name("private_tournament_round_delivery_gap")
    count = _run_invariant_sql(
        check.sql,
        check.params,
        _private_schema()
        + """
        INSERT INTO worker_task_heartbeats VALUES (
            '__production_reliability_migration_baseline__',
            '2026-07-04 10:00:00+00:00'
        );
        INSERT INTO tournaments VALUES (
            't-old-active', 'PRIVATE', 'ROUND_3', 3, '2026-07-12 12:00:00+00:00',
            '2026-07-05 11:00:00+00:00'
        );
        INSERT INTO tournament_participants VALUES ('t-old-active', 1);
        """,
    )

    assert count == 1


def test_private_tournament_gap_includes_recently_completed_old_tournament() -> None:
    check = _check_by_name("private_tournament_round_delivery_gap")
    count = _run_invariant_sql(
        check.sql,
        check.params,
        _private_schema()
        + """
        INSERT INTO tournaments VALUES (
            't-old-completed', 'PRIVATE', 'COMPLETED', 3, NULL,
            '2026-07-05 11:00:00+00:00'
        );
        INSERT INTO tournament_participants VALUES ('t-old-completed', 1);
        INSERT INTO tournament_matches VALUES (
            't-old-completed', '2026-07-10 11:00:00+00:00'
        );
        """,
    )

    assert count == 1


def test_private_tournament_gap_ignores_ancient_completed_tournament() -> None:
    check = _check_by_name("private_tournament_round_delivery_gap")
    count = _run_invariant_sql(
        check.sql,
        check.params,
        _private_schema()
        + """
        INSERT INTO tournaments VALUES (
            't-ancient', 'PRIVATE', 'COMPLETED', 3, NULL,
            '2026-07-01 11:00:00+00:00'
        );
        INSERT INTO tournament_participants VALUES ('t-ancient', 1);
        INSERT INTO tournament_matches VALUES (
            't-ancient', '2026-07-01 11:00:00+00:00'
        );
        """,
    )

    assert count == 0


def test_private_checks_ignore_active_tournament_before_instrumentation() -> None:
    setup_sql = (
        _private_schema()
        + """
        INSERT INTO worker_task_heartbeats VALUES (
            '__production_reliability_migration_baseline__',
            '2026-07-10 10:00:00+00:00'
        );
        INSERT INTO tournaments VALUES (
            't-pre-instrumentation', 'PRIVATE', 'ROUND_2', 2,
            '2026-07-12 18:00:00+00:00', '2026-07-01 11:00:00+00:00'
        );
        INSERT INTO tournament_participants VALUES ('t-pre-instrumentation', 1);
    """
    )

    for name in (
        "tournament_round_expected_delivery_zero_outcomes",
        "private_tournament_round_delivery_gap",
    ):
        check = _check_by_name(name)
        assert _run_invariant_sql(check.sql, check.params, setup_sql) == 0


def test_private_checks_include_active_tournament_after_instrumentation() -> None:
    setup_sql = (
        _private_schema()
        + """
        INSERT INTO worker_task_heartbeats VALUES (
            '__production_reliability_migration_baseline__',
            '2026-07-01 10:00:00+00:00'
        );
        INSERT INTO tournaments VALUES (
            't-post-instrumentation', 'PRIVATE', 'ROUND_2', 2,
            '2026-07-03 18:00:00+00:00', '2026-07-02 11:00:00+00:00'
        );
        INSERT INTO tournament_participants VALUES ('t-post-instrumentation', 1);
    """
    )

    for name in (
        "tournament_round_expected_delivery_zero_outcomes",
        "private_tournament_round_delivery_gap",
    ):
        check = _check_by_name(name)
        assert _run_invariant_sql(check.sql, check.params, setup_sql) == 1


def _check_by_name(name: str) -> InvariantCheck:
    return next(check for check in build_invariant_checks(NOW_UTC) if check.name == name)


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


def _private_schema() -> str:
    return """
    CREATE TABLE tournaments (
        id TEXT, type TEXT, status TEXT, current_round INTEGER,
        round_deadline TEXT, created_at TEXT
    );
    CREATE TABLE tournament_participants (tournament_id TEXT, user_id INTEGER);
    CREATE TABLE telegram_delivery_attempts (
        flow TEXT, correlation_id TEXT, target_id TEXT, status TEXT
    );
    CREATE TABLE tournament_matches (tournament_id TEXT, deadline TEXT);
    CREATE TABLE worker_task_heartbeats (schedule_key TEXT, last_success_at TEXT);
    """
