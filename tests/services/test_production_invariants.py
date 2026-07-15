from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.production_invariants import (
    InvariantCheck,
    InvariantResult,
    build_invariant_checks,
    exit_code_for,
    read_only_sql_texts,
    record_alerts_for_results,
    render_json,
    render_text,
)
from app.workers.task_heartbeat import CriticalTaskHeartbeat

NOW_UTC = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def test_production_invariant_checks_include_required_p1_surfaces() -> None:
    names = {
        check.name
        for check in build_invariant_checks(
            NOW_UTC,
            heartbeat_registry=(
                CriticalTaskHeartbeat(
                    task_name="task",
                    schedule_key="schedule",
                    stale_after_seconds=120,
                ),
            ),
        )
    }

    assert {
        "paid_without_entitlement",
        "paid_uncredited_age_minutes",
        "paid_without_charge_id",
        "reconciliation_diff_nonzero",
        "daily_cup_expected_delivery_zero_outcomes",
        "daily_cup_round_delivery_gap",
        "daily_cup_cancel_message_gap",
        "tournament_round_expected_delivery_zero_outcomes",
        "private_tournament_round_delivery_gap",
        "telegram_delivery_failure_rate",
        "telegram_blocked_users_count",
        "worker_task_heartbeat_stale",
        "queue_oldest_message_age_seconds",
        "streak_update_stale",
        "global_best_streak_source_inconsistent",
        "analytics_daily_stale",
        "telegram_delivery_pending_stale",
    }.issubset(names)


def test_production_invariant_sql_is_read_only() -> None:
    forbidden = re.compile(
        r"\b(insert|update|delete|merge|alter|drop|create|truncate|grant|revoke)\b",
        re.IGNORECASE,
    )

    assert read_only_sql_texts()
    for sql in read_only_sql_texts():
        assert forbidden.search(sql) is None


def test_stale_pending_check_covers_all_telegram_delivery_flows() -> None:
    check = next(
        check
        for check in build_invariant_checks(NOW_UTC)
        if check.name == "telegram_delivery_pending_stale"
    )

    assert "telegram_delivery_attempts" in check.sql
    assert "flow =" not in check.sql
    assert "status = 'PENDING'" in check.sql
    assert "offers_impressions" not in check.sql
    assert "telegram_delivery_pending_cutoff" in check.params


def test_daily_cup_delivery_gap_is_per_active_participant_and_not_canceled() -> None:
    check = _check_by_name("daily_cup_round_delivery_gap")

    assert "FROM tournament_participants p" in check.sql
    assert "JOIN users u ON u.id = p.user_id" in check.sql
    assert "u.status = 'ACTIVE'" in check.sql
    assert "p.user_id::text || ':phase:'" in check.sql
    assert "WHEN t.status = 'COMPLETED' THEN 'status:completed'" in check.sql
    assert "'round:' || GREATEST(1, t.current_round)::text" in check.sql
    assert "':status:' || lower(t.status)" in check.sql
    assert "d.status IN ('PENDING','SENT','FAILED','SKIPPED')" in check.sql
    assert "'CANCELED'" not in check.sql


def test_daily_cup_zero_outcome_check_uses_active_eligible_users_only() -> None:
    check = _check_by_name("daily_cup_expected_delivery_zero_outcomes")

    assert "JOIN users u ON u.id = p.user_id" in check.sql
    assert "u.status = 'ACTIVE'" in check.sql
    assert "'CANCELED'" not in check.sql


def test_streak_stale_check_correlates_activity_to_same_user() -> None:
    check = _check_by_name("streak_update_stale")

    assert "SELECT user_id, max(answered_at)" in check.sql
    assert "GROUP BY user_id" in check.sql
    assert "LEFT JOIN streak_state s ON s.user_id = a.user_id" in check.sql
    assert "s.updated_at < a.latest_answered_at" in check.sql


def test_blocked_user_check_matches_active_candidate_policy() -> None:
    check = _check_by_name("telegram_blocked_users_count")

    assert "WITH blocked_candidates AS" in check.sql
    assert "status = 'FAILED'" in check.sql
    assert "coalesce(failed_at, updated_at, created_at) >= :blocked_since" in check.sql
    assert "u.last_seen_at > b.blocked_at" in check.sql


def test_blocked_user_check_counts_fresh_candidate() -> None:
    count = _blocked_count(
        """
        INSERT INTO telegram_delivery_attempts VALUES (
            'FAILED', 101, 1, '2026-07-10 11:00:00+00:00',
            '2026-07-10 11:00:00+00:00', '2026-07-10 11:00:00+00:00'
        );
        """
    )

    assert count == 1


def test_blocked_user_check_ignores_candidate_after_newer_inbound_activity() -> None:
    count = _blocked_count(
        """
        INSERT INTO telegram_delivery_attempts VALUES (
            'FAILED', 101, 1, '2026-07-10 11:00:00+00:00',
            '2026-07-10 11:00:00+00:00', '2026-07-10 11:00:00+00:00'
        );
        INSERT INTO users VALUES (101, '2026-07-10 11:30:00+00:00');
        """
    )

    assert count == 0


def test_blocked_user_check_ignores_expired_candidate() -> None:
    count = _blocked_count(
        """
        INSERT INTO telegram_delivery_attempts VALUES (
            'FAILED', 101, 1, '2026-05-01 11:00:00+00:00',
            '2026-05-01 11:00:00+00:00', '2026-05-01 11:00:00+00:00'
        );
        """
    )

    assert count == 0


def test_blocked_user_check_ignores_non_blocking_failure() -> None:
    count = _blocked_count(
        """
        INSERT INTO telegram_delivery_attempts VALUES (
            'FAILED', 101, 0, '2026-07-10 11:00:00+00:00',
            '2026-07-10 11:00:00+00:00', '2026-07-10 11:00:00+00:00'
        );
        """
    )

    assert count == 0


def test_daily_cup_gap_counts_missing_current_phase_participant() -> None:
    check = _check_by_name("daily_cup_round_delivery_gap")
    count = _run_invariant_sql(
        check.sql,
        check.params,
        """
        CREATE TABLE tournaments (
            id TEXT, type TEXT, status TEXT, current_round INTEGER, round_start_time TEXT, created_at TEXT
        );
        CREATE TABLE tournament_matches (tournament_id TEXT, round_no INTEGER, deadline TEXT);
        CREATE TABLE tournament_participants (tournament_id TEXT, user_id INTEGER);
        CREATE TABLE users (id INTEGER, status TEXT);
        CREATE TABLE telegram_delivery_attempts (
            flow TEXT, correlation_id TEXT, target_id TEXT, status TEXT
        );
        CREATE TABLE worker_task_heartbeats (schedule_key TEXT, last_success_at TEXT);
        INSERT INTO tournaments VALUES ('cup-1', 'DAILY_ARENA', 'ROUND_2', 2, '2026-07-10 11:00:00+00:00', '2026-07-10 09:00:00+00:00');
        INSERT INTO users VALUES (1, 'ACTIVE'), (2, 'ACTIVE');
        INSERT INTO tournament_participants VALUES ('cup-1', 1), ('cup-1', 2);
        INSERT INTO telegram_delivery_attempts VALUES (
            'daily_cup_round_messaging', 'cup-1',
            '1:phase:round:2:status:round_2:edit:101', 'SENT'
        );
        INSERT INTO telegram_delivery_attempts VALUES (
            'daily_cup_round_messaging', 'cup-1',
            '2:phase:round:1:status:round_1:edit:202', 'SENT'
        );
        """,
    )

    assert count == 1


def test_daily_cup_gap_ignores_inactive_and_canceled_without_false_alert() -> None:
    check = _check_by_name("daily_cup_round_delivery_gap")
    count = _run_invariant_sql(
        check.sql,
        check.params,
        """
        CREATE TABLE tournaments (
            id TEXT, type TEXT, status TEXT, current_round INTEGER, round_start_time TEXT, created_at TEXT
        );
        CREATE TABLE tournament_matches (tournament_id TEXT, round_no INTEGER, deadline TEXT);
        CREATE TABLE tournament_participants (tournament_id TEXT, user_id INTEGER);
        CREATE TABLE users (id INTEGER, status TEXT);
        CREATE TABLE telegram_delivery_attempts (
            flow TEXT, correlation_id TEXT, target_id TEXT, status TEXT
        );
        CREATE TABLE worker_task_heartbeats (schedule_key TEXT, last_success_at TEXT);
        INSERT INTO tournaments VALUES ('cup-1', 'DAILY_ARENA', 'ROUND_2', 2, '2026-07-10 11:00:00+00:00', '2026-07-10 09:00:00+00:00');
        INSERT INTO tournaments VALUES ('cup-2', 'DAILY_ARENA', 'CANCELED', 0, NULL, '2026-07-10 09:00:00+00:00');
        INSERT INTO users VALUES (1, 'BLOCKED'), (2, 'ACTIVE');
        INSERT INTO tournament_participants VALUES ('cup-1', 1), ('cup-2', 2);
        """,
    )

    assert count == 0


def test_streak_stale_count_is_per_user_not_global() -> None:
    check = _check_by_name("streak_update_stale")
    count = _run_invariant_sql(
        check.sql,
        check.params,
        """
        CREATE TABLE quiz_attempts (user_id INTEGER, answered_at TEXT);
        CREATE TABLE streak_state (user_id INTEGER, updated_at TEXT);
        INSERT INTO quiz_attempts VALUES (1, '2026-07-10 11:00:00+00:00');
        INSERT INTO quiz_attempts VALUES (2, '2026-07-10 11:30:00+00:00');
        INSERT INTO streak_state VALUES (1, '2026-07-10 11:05:00+00:00');
        INSERT INTO streak_state VALUES (2, '2026-07-10 11:00:00+00:00');
        """,
    )

    assert count == 1


def test_streak_stale_count_finds_missing_user_row() -> None:
    check = _check_by_name("streak_update_stale")
    count = _run_invariant_sql(
        check.sql,
        check.params,
        """
        CREATE TABLE quiz_attempts (user_id INTEGER, answered_at TEXT);
        CREATE TABLE streak_state (user_id INTEGER, updated_at TEXT);
        INSERT INTO quiz_attempts VALUES (1, '2026-07-10 11:00:00+00:00');
        INSERT INTO quiz_attempts VALUES (2, '2026-07-10 11:30:00+00:00');
        INSERT INTO streak_state VALUES (1, '2026-07-10 11:05:00+00:00');
        """,
    )

    assert count == 1


def test_streak_stale_count_has_no_finding_without_recent_quiz_activity() -> None:
    check = _check_by_name("streak_update_stale")
    count = _run_invariant_sql(
        check.sql,
        check.params,
        """
        CREATE TABLE quiz_attempts (user_id INTEGER, answered_at TEXT);
        CREATE TABLE streak_state (user_id INTEGER, updated_at TEXT);
        INSERT INTO streak_state VALUES (1, '2026-07-10 11:05:00+00:00');
        """,
    )

    assert count == 0


def test_production_invariant_exit_code_blocks_only_p0_p1_failures() -> None:
    p2_only = [
        _result(name="analytics_daily_stale", status="FAIL", severity="P2", count=1),
    ]
    p1_failure = [
        _result(name="paid_without_entitlement", status="FAIL", severity="P1", count=1),
    ]

    assert exit_code_for(p2_only) == 0
    assert exit_code_for(p1_failure) == 1


def test_production_invariant_renderers_are_safe_and_stable() -> None:
    result = _result(name="telegram_blocked_users_count", status="FAIL", severity="P2", count=3)

    text = render_text([result])
    payload = render_json([result])

    assert "telegram_blocked_users_count" in text
    assert "telegram_user_id" not in text
    assert '"safe_context"' in payload
    assert '"count": 3' in payload


async def test_record_alerts_for_results_dedupes_and_resolves(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def _record_open(_session, **kwargs) -> None:
        calls.append(("open", kwargs))

    async def _mark_resolved(_session, **kwargs) -> int:
        calls.append(("resolved", kwargs))
        return 1

    from app.services import production_invariants

    monkeypatch.setattr(
        production_invariants.ProductionInvariantAlertsRepo,
        "record_open",
        _record_open,
    )
    monkeypatch.setattr(
        production_invariants.ProductionInvariantAlertsRepo,
        "mark_resolved",
        _mark_resolved,
    )

    summary = await record_alerts_for_results(
        cast(AsyncSession, object()),
        results=[
            _result(name="paid_without_entitlement", status="FAIL", severity="P1", count=2),
            _result(name="analytics_daily_stale", status="OK", severity="P2", count=0),
        ],
        seen_at=NOW_UTC,
    )

    assert summary == {"opened_or_updated": 1, "resolved": 1}
    assert calls[0][0] == "open"
    assert calls[0][1]["alert_type"] == "paid_without_entitlement"
    assert calls[1][0] == "resolved"


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


def _blocked_count(rows_sql: str) -> int:
    check = _check_by_name("telegram_blocked_users_count")
    return _run_invariant_sql(
        check.sql,
        check.params,
        """
        CREATE TABLE telegram_delivery_attempts (
            status TEXT,
            telegram_user_id INTEGER,
            is_blocked_candidate INTEGER,
            failed_at TEXT,
            updated_at TEXT,
            created_at TEXT
        );
        CREATE TABLE users (telegram_user_id INTEGER, last_seen_at TEXT);
        """
        + rows_sql,
    )


def _result(*, name: str, status: str, severity: str, count: int) -> InvariantResult:
    return InvariantResult(
        name=name,
        status=status,
        severity=severity,
        count=count,
        description=f"{name} description",
        correlation_key=name,
        safe_context={"check_name": name, "count": count},
    )
