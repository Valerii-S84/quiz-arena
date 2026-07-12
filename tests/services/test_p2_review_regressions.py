from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.services import telegram_delivery
from app.services.production_invariant_checks.delivery_daily import build_daily_cup_delivery_checks
from app.services.production_invariant_checks.delivery_telegram import (
    build_telegram_delivery_checks,
)
from app.services.production_invariant_checks.heartbeat import build_heartbeat_checks
from app.services.telegram_delivery_types import TelegramDeliveryFailure
from app.workers.task_heartbeat import CriticalTaskHeartbeat
from tests.type_helpers import AsyncBeginContext

NOW_UTC = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("check_name", "status"),
    [
        ("daily_cup_expected_delivery_zero_outcomes", "ROUND_1"),
        ("daily_cup_round_delivery_gap", "ROUND_1"),
        ("daily_cup_cancel_message_gap", "CANCELED"),
    ],
)
def test_daily_cup_checks_ignore_pre_instrumentation_tournaments(
    check_name: str,
    status: str,
) -> None:
    check = next(
        check
        for check in build_daily_cup_delivery_checks(NOW_UTC - timedelta(days=2))
        if check.name == check_name
    )

    count = _run_sql(
        check.sql,
        check.params,
        f"""
        CREATE TABLE tournaments (
            id TEXT, type TEXT, status TEXT, current_round INTEGER, created_at TEXT
        );
        CREATE TABLE tournament_participants (tournament_id TEXT, user_id INTEGER);
        CREATE TABLE users (id INTEGER, telegram_user_id INTEGER, status TEXT);
        CREATE TABLE telegram_delivery_attempts (
            flow TEXT, correlation_id TEXT, target_id TEXT,
            telegram_user_id INTEGER, status TEXT
        );
        CREATE TABLE worker_task_heartbeats (
            schedule_key TEXT, last_success_at TEXT
        );
        INSERT INTO worker_task_heartbeats VALUES (
            '__production_reliability_migration_baseline__', '2026-07-12 10:00:00+00:00'
        );
        INSERT INTO tournaments VALUES (
            'cup-old', 'DAILY_ARENA', '{status}', 1, '2026-07-11 12:00:00+00:00'
        );
        INSERT INTO users VALUES (1, 1001, 'ACTIVE');
        INSERT INTO tournament_participants VALUES ('cup-old', 1);
        """,
    )

    assert count == 0


@pytest.mark.parametrize(
    ("last_started_at", "expected"),
    [
        ("2026-07-12 11:59:30+00:00", 0),
        ("2026-07-12 11:50:00+00:00", 1),
    ],
)
def test_first_heartbeat_run_uses_started_at_grace(
    last_started_at: str,
    expected: int,
) -> None:
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

    count = _run_sql(
        check.sql,
        check.params,
        f"""
        CREATE TABLE worker_task_heartbeats (
            task_name TEXT, schedule_key TEXT, last_success_at TEXT,
            consecutive_failures INTEGER, last_started_at TEXT
        );
        INSERT INTO worker_task_heartbeats VALUES (
            'task', 'schedule', NULL, 0, '{last_started_at}'
        );
        """,
    )

    assert count == expected


def test_failure_rate_counts_recent_retried_failures() -> None:
    check = next(
        check
        for check in build_telegram_delivery_checks(NOW_UTC)
        if check.name == "telegram_delivery_failure_rate"
    )
    rows = ",".join(
        "('FAILED', '2026-07-12 09:00:00+00:00', "
        "'2026-07-12 11:50:00+00:00', '2026-07-12 11:50:00+00:00')"
        for _ in range(10)
    )

    count = _run_sql(
        check.sql,
        check.params,
        """
        CREATE TABLE telegram_delivery_attempts (
            status TEXT, created_at TEXT, updated_at TEXT, failed_at TEXT
        );
        """
        + f"INSERT INTO telegram_delivery_attempts VALUES {rows};",
    )

    assert count == 1


class _SessionLocal:
    def begin(self) -> AsyncBeginContext[str]:
        return AsyncBeginContext("session")


@pytest.mark.parametrize(
    "helper",
    ["sent", "failed", "failed_with_classification"],
)
async def test_terminal_helpers_raise_when_cas_lease_is_lost(
    monkeypatch: pytest.MonkeyPatch,
    helper: str,
) -> None:
    async def _lost(*_args, **_kwargs) -> int:
        return 0

    failure = TelegramDeliveryFailure(
        failure_code="TELEGRAM_UNKNOWN",
        failure_reason="failure",
        telegram_error_code=None,
        is_blocked_candidate=False,
    )
    call: Any
    if helper == "sent":
        monkeypatch.setattr(telegram_delivery.TelegramDeliveryAttemptsRepo, "mark_sent", _lost)
        call = telegram_delivery.mark_telegram_delivery_sent(
            idempotency_key="delivery",
            happened_at=NOW_UTC,
            session_local=_SessionLocal(),
        )
    elif helper == "failed":
        monkeypatch.setattr(telegram_delivery.TelegramDeliveryAttemptsRepo, "mark_failed", _lost)
        call = telegram_delivery.mark_telegram_delivery_failed(
            idempotency_key="delivery",
            happened_at=NOW_UTC,
            exc=RuntimeError("send failed"),
            session_local=_SessionLocal(),
        )
    else:
        monkeypatch.setattr(telegram_delivery.TelegramDeliveryAttemptsRepo, "mark_failed", _lost)
        call = telegram_delivery.mark_telegram_delivery_failed_with_classification(
            idempotency_key="delivery",
            happened_at=NOW_UTC,
            failure=failure,
            failure_reason="classified failure",
            session_local=_SessionLocal(),
        )

    with pytest.raises(RuntimeError, match="terminal lease was lost"):
        await call


async def test_skipped_terminal_helper_raises_when_cas_lease_is_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _create(*_args, **_kwargs):
        return SimpleNamespace(status="PENDING"), True

    async def _lost(*_args, **_kwargs) -> int:
        return 0

    monkeypatch.setattr(
        telegram_delivery.TelegramDeliveryAttemptsRepo,
        "create_pending_once",
        _create,
    )
    monkeypatch.setattr(
        telegram_delivery.TelegramDeliveryAttemptsRepo,
        "mark_skipped",
        _lost,
    )
    target = cast(
        Any,
        SimpleNamespace(
            idempotency_key="delivery",
            flow="flow",
            task_name="task",
            correlation_id="correlation",
            target_type="user",
            target_id="1",
            telegram_user_id=None,
            chat_id=None,
            safe_context={},
        ),
    )

    with pytest.raises(RuntimeError, match="skipped terminal lease was lost"):
        await telegram_delivery.record_telegram_delivery_skipped(
            target=target,
            happened_at=NOW_UTC,
            failure_code="SKIPPED",
            failure_reason="skip",
            session_local=_SessionLocal(),
        )


def _run_sql(sql: str, params: dict[str, object], setup_sql: str) -> int:
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
