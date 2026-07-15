from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects import postgresql

from app.db.models.production_reliability import TelegramDeliveryAttempt
from app.db.repo.production_reliability_types import (
    TelegramDeliveryAttemptCreate,
    TelegramDeliveryFailure,
)
from app.db.repo.telegram_blocked_candidates_repo import TelegramBlockedCandidatesRepo
from app.db.repo.telegram_delivery_attempts_repo import TelegramDeliveryAttemptsRepo
from app.db.repo.telegram_delivery_retry_repo import TelegramDeliveryRetryRepo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import ScalarResult, ScalarsResult

UTC = timezone.utc


def compile_parameterized_statement(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def _attempt(**overrides: object) -> TelegramDeliveryAttempt:
    payload: dict[str, object] = {
        "id": 1,
        "flow": "daily_cup",
        "task_name": "daily_cup.round_delivery",
        "correlation_id": "round:1",
        "idempotency_key": "delivery:daily:1",
        "target_type": "daily_cup_round",
        "target_id": "1",
        "safe_context": {"source": "test"},
    }
    payload.update(overrides)
    return TelegramDeliveryAttempt(**payload)


async def test_delivery_attempt_create_once_uses_idempotency_key() -> None:
    row = _attempt()
    session = RecordingSession(ScalarResult(row))

    created, was_created = await TelegramDeliveryAttemptsRepo.create_once(
        session,
        attempt=TelegramDeliveryAttemptCreate(
            flow="daily_cup",
            task_name="daily_cup.round_delivery",
            correlation_id="round:1",
            idempotency_key="delivery:daily:1",
            target_type="daily_cup_round",
            target_id="1",
            safe_context={"source": "test"},
        ),
    )

    assert created is row
    assert was_created is True
    sql = compile_parameterized_statement(session.statement)
    assert "INSERT INTO telegram_delivery_attempts" in sql
    assert "ON CONFLICT (idempotency_key) DO NOTHING" in sql
    assert "raw_payload" not in sql


async def test_delivery_attempt_status_updates_are_scoped_by_idempotency_key() -> None:
    sent_session = RecordingSession(ScalarResult(1))
    assert (
        await TelegramDeliveryAttemptsRepo.mark_sent(
            sent_session,
            idempotency_key="delivery:daily:1",
        )
        is True
    )
    sent_sql = compile_statement(sent_session.statement)
    assert "UPDATE telegram_delivery_attempts SET" in sent_sql
    assert "status='SENT'" in sent_sql
    assert "telegram_delivery_attempts.idempotency_key = 'delivery:daily:1'" in sent_sql

    failed_session = RecordingSession(ScalarResult(1))
    assert (
        await TelegramDeliveryAttemptsRepo.mark_failed(
            failed_session,
            idempotency_key="delivery:daily:1",
            failure=TelegramDeliveryFailure(
                failure_code="TELEGRAM_FORBIDDEN",
                failure_reason="blocked",
                telegram_error_code=403,
                is_blocked_candidate=True,
            ),
        )
        is True
    )
    failed_sql = compile_statement(failed_session.statement)
    assert "status='FAILED'" in failed_sql
    assert "failure_code='TELEGRAM_FORBIDDEN'" in failed_sql
    assert "is_blocked_candidate=true" in failed_sql


async def test_blocked_candidates_query_filters_candidates_since_timestamp() -> None:
    since_utc = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
    row = _attempt(is_blocked_candidate=True)
    session = RecordingSession(ScalarsResult([row]))

    assert await TelegramBlockedCandidatesRepo.list_recent(
        session,
        since_utc=since_utc,
        flow="daily_cup",
        limit=0,
    ) == [row]

    sql = compile_statement(session.statement)
    assert "telegram_delivery_attempts.is_blocked_candidate IS true" in sql
    assert "telegram_delivery_attempts.created_at >= '2026-07-16 12:00:00+00:00'" in sql
    assert "telegram_delivery_attempts.flow = 'daily_cup'" in sql
    assert "LIMIT 1" in sql


async def test_retry_claim_uses_pending_rows_with_skip_locked() -> None:
    row = _attempt(attempt_count=1)
    session = RecordingSession(ScalarsResult([row]))

    assert await TelegramDeliveryRetryRepo.claim_pending_batch(
        session,
        flow="daily_cup",
        limit=10,
    ) == [row]

    sql = compile_statement(session.statement)
    assert "UPDATE telegram_delivery_attempts SET" in sql
    assert "attempt_count=(telegram_delivery_attempts.attempt_count + 1)" in sql
    assert "telegram_delivery_attempts.status = 'PENDING'" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
