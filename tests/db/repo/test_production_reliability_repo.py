from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

from sqlalchemy.dialects import postgresql

from app.db.models.production_reliability import (
    ProductionInvariantAlert,
    TelegramDeliveryAttempt,
    WorkerTaskHeartbeat,
)
from app.db.repo.production_reliability_repo import (
    DeliveryAttemptCreate,
    ProductionInvariantAlertsRepo,
    TelegramDeliveryAttemptsRepo,
    WorkerTaskHeartbeatsRepo,
    hash_chat_id,
    safe_error_hash,
)
from tests.db.repo._helpers import RecordingSession
from tests.type_helpers import ScalarResult

NOW_UTC = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def compile_parameterized_statement(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


async def test_delivery_attempt_create_once_uses_idempotency_key() -> None:
    row = TelegramDeliveryAttempt(
        flow="daily_cup",
        task_name="task",
        correlation_id="cup:1",
        idempotency_key="delivery:daily:1:11",
        target_type="user",
        target_id="11",
        telegram_user_id=101,
        chat_id_hash=hash_chat_id(101),
    )
    session = RecordingSession(ScalarResult(row))

    created, was_created = await TelegramDeliveryAttemptsRepo.create_pending_once(
        session,
        item=DeliveryAttemptCreate(
            flow="daily_cup",
            task_name="task",
            correlation_id="cup:1",
            idempotency_key="delivery:daily:1:11",
            target_type="user",
            target_id="11",
            telegram_user_id=101,
            chat_id_hash=hash_chat_id(101),
            safe_context={"tournament_id": "1"},
        ),
    )

    assert created is row
    assert was_created is True
    sql = compile_parameterized_statement(session.statement)
    assert "INSERT INTO telegram_delivery_attempts" in sql
    assert "ON CONFLICT (idempotency_key) DO NOTHING" in sql
    assert "chat_id_hash" in sql
    assert "chat_id)" not in sql


async def test_delivery_attempt_mark_failed_sets_blocked_candidate() -> None:
    session = RecordingSession(ScalarResult(None))

    await TelegramDeliveryAttemptsRepo.mark_failed(
        session,
        idempotency_key="delivery:1",
        failed_at=NOW_UTC,
        failure_code="TELEGRAM_FORBIDDEN",
        failure_reason="bot blocked by user",
        telegram_error_code=403,
        is_blocked_candidate=True,
    )

    sql = compile_parameterized_statement(session.statement)
    assert "UPDATE telegram_delivery_attempts" in sql
    assert "status=%(status)s" in sql
    assert "telegram_delivery_attempts.status = %(status_1)s" in sql
    assert "is_blocked_candidate" in sql
    assert "attempt_count=(telegram_delivery_attempts.attempt_count + %(attempt_count_1)s)" in sql


async def test_delivery_attempt_terminal_updates_only_touch_pending_rows() -> None:
    sent_session = RecordingSession(ScalarResult(None))
    skipped_session = RecordingSession(ScalarResult(None))

    await TelegramDeliveryAttemptsRepo.mark_sent(
        sent_session,
        idempotency_key="delivery:sent",
        sent_at=NOW_UTC,
    )
    await TelegramDeliveryAttemptsRepo.mark_skipped(
        skipped_session,
        idempotency_key="delivery:skip",
        skipped_at=NOW_UTC,
        failure_code="ALREADY_SENT",
        failure_reason="duplicate target",
    )

    sent_sql = compile_parameterized_statement(sent_session.statement)
    skipped_sql = compile_parameterized_statement(skipped_session.statement)
    assert "telegram_delivery_attempts.status = %(status_1)s" in sent_sql
    assert "telegram_delivery_attempts.status = %(status_1)s" in skipped_sql


async def test_delivery_attempt_retry_claim_is_bounded_to_retryable_failures() -> None:
    session = RecordingSession(SimpleNamespace(rowcount=1))

    await TelegramDeliveryAttemptsRepo.claim_retryable_attempt(
        session,
        idempotency_key="delivery:retry",
        claimed_at=NOW_UTC,
        retryable_failure_codes=frozenset({"TELEGRAM_RETRY_AFTER"}),
        stale_pending_before=NOW_UTC,
        max_attempts=3,
        allow_stale_pending_retry=False,
    )

    sql = compile_parameterized_statement(session.statement)
    assert "UPDATE telegram_delivery_attempts" in sql
    assert "telegram_delivery_attempts.attempt_count < %(attempt_count_1)s" in sql
    assert "telegram_delivery_attempts.failure_code IN" in sql
    assert "telegram_delivery_attempts.is_blocked_candidate IS false" in sql
    assert "telegram_delivery_attempts.updated_at <= %(updated_at_1)s" not in sql


async def test_delivery_attempt_retry_claim_can_include_safe_stale_pending() -> None:
    session = RecordingSession(SimpleNamespace(rowcount=1))

    await TelegramDeliveryAttemptsRepo.claim_retryable_attempt(
        session,
        idempotency_key="delivery:retry",
        claimed_at=NOW_UTC,
        retryable_failure_codes=frozenset({"TELEGRAM_RETRY_AFTER"}),
        stale_pending_before=NOW_UTC,
        max_attempts=3,
        allow_stale_pending_retry=True,
    )

    sql = compile_parameterized_statement(session.statement)
    assert "telegram_delivery_attempts.status = %(status_2)s" in sql
    assert "telegram_delivery_attempts.updated_at <= %(updated_at_1)s" in sql


async def test_blocked_candidate_ignores_rows_with_newer_user_activity() -> None:
    session = RecordingSession(ScalarResult(None))

    await TelegramDeliveryAttemptsRepo.has_blocked_candidate(
        session,
        telegram_user_id=101,
        blocked_since=NOW_UTC,
    )

    sql = compile_parameterized_statement(session.statement)
    assert "telegram_delivery_attempts.is_blocked_candidate IS true" in sql
    assert "telegram_delivery_attempts.status = %(status_1)s" in sql
    assert "users.telegram_user_id = %(telegram_user_id_2)s" in sql
    assert "users.last_seen_at > coalesce(" in sql


async def test_worker_heartbeat_started_uses_task_schedule_conflict_key() -> None:
    session = RecordingSession(ScalarResult(None))

    await WorkerTaskHeartbeatsRepo.record_started(
        session,
        task_name="app.workers.tasks.daily_cup.advance_rounds",
        schedule_key="daily-cup-round-advance",
        started_at=NOW_UTC,
    )

    sql = compile_parameterized_statement(session.statement)
    assert "INSERT INTO worker_task_heartbeats" in sql
    assert "ON CONFLICT (task_name, schedule_key) DO UPDATE" in sql
    assert "last_started_at" in sql


async def test_worker_heartbeat_failure_increments_consecutive_failures() -> None:
    session = RecordingSession(ScalarResult(None))

    await WorkerTaskHeartbeatsRepo.record_failure(
        session,
        task_name="task",
        schedule_key="schedule",
        failed_at=NOW_UTC,
        duration_ms=123,
        error_hash=safe_error_hash("boom"),
    )

    sql = compile_parameterized_statement(session.statement)
    assert "INSERT INTO worker_task_heartbeats" in sql
    assert "consecutive_failures" in sql
    assert "(worker_task_heartbeats.consecutive_failures + %(consecutive_failures_1)s)" in sql


async def test_invariant_alert_record_open_dedupes_by_type_key_status() -> None:
    session = RecordingSession(ScalarResult(None), ScalarResult(None), ScalarResult(None))

    await ProductionInvariantAlertsRepo.record_open(
        session,
        severity="P1",
        alert_type="worker_task_heartbeat_stale",
        correlation_key="task:daily-cup-round-advance",
        seen_at=NOW_UTC,
        safe_context={"task_name": "task"},
    )

    open_lookup_sql = compile_parameterized_statement(session.statements[0])
    terminal_lookup_sql = compile_parameterized_statement(session.statements[1])
    insert_sql = compile_parameterized_statement(session.statements[2])
    assert "SELECT production_invariant_alerts.id" in open_lookup_sql
    assert "production_invariant_alerts.status = %(status_1)s" in open_lookup_sql
    assert "production_invariant_alerts.status IN" in terminal_lookup_sql
    assert "INSERT INTO production_invariant_alerts" in insert_sql
    assert "ON CONFLICT (type, correlation_key, status) DO UPDATE" in insert_sql
    assert "count = (production_invariant_alerts.count + %(count_1)s)" in insert_sql


async def test_invariant_alert_reopen_terminal_rows_reuses_type_key() -> None:
    session = RecordingSession(ScalarResult(None), ScalarResult(42), ScalarResult(None))

    await ProductionInvariantAlertsRepo._reopen_existing_terminal(
        session,
        severity="P1",
        alert_type="worker_task_heartbeat_stale",
        correlation_key="task:daily-cup-round-advance",
        seen_at=NOW_UTC,
        safe_context={"task_name": "task"},
    )

    sql = compile_parameterized_statement(session.statements[2])
    assert "UPDATE production_invariant_alerts" in sql
    assert "status=%(status)s" in sql
    assert "resolved_at=%(resolved_at)s" in sql
    assert "acked_at=%(acked_at)s" in sql
    assert "count=(production_invariant_alerts.count + %(count_1)s)" in sql


async def test_invariant_alert_reopen_terminal_lookup_includes_acked_rows() -> None:
    session = RecordingSession(ScalarResult(None), ScalarResult(42), SimpleNamespace(rowcount=1))

    await ProductionInvariantAlertsRepo._reopen_existing_terminal(
        session,
        severity="P1",
        alert_type="worker_task_heartbeat_stale",
        correlation_key="task:daily-cup-round-advance",
        seen_at=NOW_UTC,
        safe_context={"task_name": "task"},
    )

    compiled = cast(Any, session.statements[1]).compile(dialect=postgresql.dialect())
    assert compiled.params["status_1"] == ["RESOLVED", "ACKED"]


async def test_invariant_alert_record_open_returns_after_successful_reopen() -> None:
    session = RecordingSession(ScalarResult(None), ScalarResult(42), SimpleNamespace(rowcount=1))

    await ProductionInvariantAlertsRepo.record_open(
        session,
        severity="P1",
        alert_type="worker_task_heartbeat_stale",
        correlation_key="task:daily-cup-round-advance",
        seen_at=NOW_UTC,
        safe_context={"task_name": "task"},
    )

    assert len(session.statements) == 3
    sql = compile_parameterized_statement(session.statements[2])
    assert "UPDATE production_invariant_alerts" in sql
    assert "count=(production_invariant_alerts.count + %(count_1)s)" in sql
    assert "INSERT INTO production_invariant_alerts" not in sql


def test_reliability_models_are_importable() -> None:
    assert TelegramDeliveryAttempt.__tablename__ == "telegram_delivery_attempts"
    assert WorkerTaskHeartbeat.__tablename__ == "worker_task_heartbeats"
    assert ProductionInvariantAlert.__tablename__ == "production_invariant_alerts"
