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
from app.workers.task_heartbeat_registry import CriticalTaskHeartbeat

NOW_UTC = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def test_checker_covers_current_durable_surfaces_without_unsupported_daily_rounds() -> None:
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
    assert "daily_cup_round_delivery_gap" not in names
    assert "daily_cup_expected_delivery_zero_outcomes" not in names


def test_checker_sql_is_read_only() -> None:
    forbidden = re.compile(
        r"\b(insert|update|delete|merge|alter|drop|create|truncate|grant|revoke)\b",
        re.IGNORECASE,
    )

    assert read_only_sql_texts()
    assert all(forbidden.search(sql) is None for sql in read_only_sql_texts())


def test_daily_cup_cancel_check_matches_current_attempt_contract() -> None:
    check = _check_by_name("daily_cup_cancel_message_gap")

    assert "d.flow = 'daily_cup'" in check.sql
    assert "d.task_name = 'daily_cup.cancel_delivery'" in check.sql
    assert "('daily_cup_cancel:' || t.id::text)" in check.sql
    assert "d.target_type = 'daily_cup_cancel'" in check.sql
    assert "d.telegram_user_id = u.telegram_user_id" in check.sql


def test_private_tournament_gap_matches_current_phase_target_ids() -> None:
    check = _check_by_name("private_tournament_round_delivery_gap")

    assert "t.type = 'PRIVATE'" in check.sql
    assert "p.user_id::text || ':phase:'" in check.sql
    assert "WHEN t.status = 'COMPLETED' THEN 'status:completed'" in check.sql
    assert "'round:' || GREATEST(1, t.current_round)::text" in check.sql
    assert "d.status IN ('PENDING','SENT','FAILED','SKIPPED')" in check.sql
    assert "'REGISTRATION'" not in check.sql
    assert "'CANCELED'" not in check.sql


def test_daily_cup_cancel_gap_counts_only_missing_active_target() -> None:
    check = _check_by_name("daily_cup_cancel_message_gap")
    count = _run_sql(
        check,
        """
        CREATE TABLE tournaments (
            id TEXT, type TEXT, status TEXT, registration_deadline TEXT
        );
        CREATE TABLE tournament_participants (tournament_id TEXT, user_id INTEGER);
        CREATE TABLE users (
            id INTEGER, telegram_user_id INTEGER, status TEXT
        );
        CREATE TABLE telegram_delivery_attempts (
            flow TEXT, task_name TEXT, correlation_id TEXT, target_type TEXT,
            target_id TEXT, telegram_user_id INTEGER, status TEXT
        );
        INSERT INTO tournaments VALUES (
            'cup-1', 'DAILY_ARENA', 'CANCELED', '2026-07-26 11:00:00+00:00'
        );
        INSERT INTO users VALUES (1, 101, 'ACTIVE'), (2, 202, 'ACTIVE');
        INSERT INTO tournament_participants VALUES ('cup-1', 1), ('cup-1', 2);
        INSERT INTO telegram_delivery_attempts VALUES (
            'daily_cup', 'daily_cup.cancel_delivery', 'daily_cup_cancel:cup-1',
            'daily_cup_cancel', 'cup-1', 101, 'SENT'
        );
        """,
    )

    assert count == 1


def test_private_tournament_gap_counts_previous_phase_as_missing() -> None:
    check = _check_by_name("private_tournament_round_delivery_gap")
    count = _run_sql(
        check,
        """
        CREATE TABLE tournaments (
            id TEXT, type TEXT, status TEXT, current_round INTEGER, round_deadline TEXT
        );
        CREATE TABLE tournament_matches (tournament_id TEXT, round_no INTEGER, deadline TEXT);
        CREATE TABLE tournament_participants (tournament_id TEXT, user_id INTEGER);
        CREATE TABLE telegram_delivery_attempts (
            flow TEXT, correlation_id TEXT, target_id TEXT, status TEXT
        );
        INSERT INTO tournaments VALUES (
            'private-1', 'PRIVATE', 'ROUND_2', 2, '2026-07-26 13:00:00+00:00'
        );
        INSERT INTO tournament_participants VALUES ('private-1', 1), ('private-1', 2);
        INSERT INTO telegram_delivery_attempts VALUES (
            'private_tournament_round_messaging', 'private-1',
            '1:phase:round:2:status:round_2:send', 'SENT'
        );
        INSERT INTO telegram_delivery_attempts VALUES (
            'private_tournament_round_messaging', 'private-1',
            '2:phase:round:1:status:round_1:send', 'SENT'
        );
        """,
    )

    assert count == 1


def test_heartbeat_checks_use_current_registry_contract() -> None:
    checks = build_invariant_checks(
        NOW_UTC,
        heartbeat_registry=(
            CriticalTaskHeartbeat("periodic", "periodic-key", 120),
            CriticalTaskHeartbeat("on-demand", "on-demand-key", None),
        ),
    )
    heartbeat_checks = [check for check in checks if check.name == "worker_task_heartbeat_stale"]

    assert len(heartbeat_checks) == 1
    assert heartbeat_checks[0].correlation_key.endswith("periodic-key")
    assert heartbeat_checks[0].safe_context["task_name"] == "periodic"


def test_exit_code_and_renderers_keep_p2_non_blocking_and_payload_safe() -> None:
    p2_result = _result(name="analytics_daily_stale", status="FAIL", severity="P2", count=1)
    p1_result = _result(name="paid_without_entitlement", status="FAIL", severity="P1", count=1)

    assert exit_code_for([p2_result]) == 0
    assert exit_code_for([p1_result]) == 1
    assert "analytics_daily_stale" in render_text([p2_result])
    assert '"safe_context"' in render_json([p2_result])
    assert "telegram_user_id" not in render_text([p2_result])


async def test_record_alerts_summarizes_actual_repository_mutations(monkeypatch) -> None:
    calls: list[str] = []

    async def _record_open(_session, **_kwargs) -> int:
        calls.append("open")
        return 0

    async def _mark_resolved(_session, **_kwargs) -> int:
        calls.append("resolved")
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

    assert summary == {"opened_or_updated": 0, "resolved": 1}
    assert calls == ["open", "resolved"]


def _check_by_name(name: str) -> InvariantCheck:
    return next(
        check
        for check in build_invariant_checks(NOW_UTC, heartbeat_registry=())
        if check.name == name
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


def _run_sql(check: InvariantCheck, setup_sql: str) -> int:
    sql = check.sql.replace("::text", "").replace("GREATEST(", "max(")
    params = {
        key: value.isoformat(sep=" ") if isinstance(value, datetime) else value
        for key, value in check.params.items()
    }
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(setup_sql)
        row = connection.execute(sql, params).fetchone()
    finally:
        connection.close()
    assert row is not None
    return int(row[0] or 0)
