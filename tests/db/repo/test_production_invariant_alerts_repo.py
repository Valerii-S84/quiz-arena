from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

from sqlalchemy.dialects import postgresql

from app.db.models.production_reliability import ProductionInvariantAlert
from app.db.repo.production_invariant_alerts_repo import ProductionInvariantAlertsRepo
from tests.db.repo._helpers import RecordingSession
from tests.type_helpers import ScalarResult

NOW_UTC = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def _compile(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def _alert(**overrides: object) -> ProductionInvariantAlert:
    values: dict[str, object] = {
        "id": 1,
        "severity": "P1",
        "type": "worker_task_heartbeat_stale",
        "correlation_key": "worker:payments",
        "status": "OPEN",
        "first_seen_at": NOW_UTC,
        "last_seen_at": NOW_UTC,
        "count": 1,
        "safe_context": {"check_name": "worker_task_heartbeat_stale"},
        "created_at": NOW_UTC,
        "updated_at": NOW_UTC,
    }
    values.update(overrides)
    return ProductionInvariantAlert(**values)


async def test_record_open_targets_partial_active_unique_index() -> None:
    session = RecordingSession(
        ScalarResult(None),
        ScalarResult(None),
        SimpleNamespace(rowcount=1),
    )

    changed = await ProductionInvariantAlertsRepo.record_open(
        session,
        severity="P1",
        alert_type="worker_task_heartbeat_stale",
        correlation_key="worker:payments",
        seen_at=NOW_UTC,
        safe_context={"check_name": "worker_task_heartbeat_stale"},
    )

    assert changed == 1
    assert "pg_advisory_xact_lock" in str(session.statements[0])
    sql = _compile(session.statements[2])
    assert "ON CONFLICT (type, correlation_key) WHERE status = 'OPEN' DO UPDATE" in sql
    assert "count = (production_invariant_alerts.count + %(count_1)s)" in sql
    assert "production_invariant_alerts.updated_at <= %(updated_at_1)s" in sql


async def test_record_open_ignores_failure_older_than_latest_episode() -> None:
    latest = _alert(status="RESOLVED", updated_at=NOW_UTC + timedelta(minutes=1))
    session = RecordingSession(ScalarResult(None), ScalarResult(latest))

    changed = await ProductionInvariantAlertsRepo.record_open(
        session,
        severity="P1",
        alert_type=latest.type,
        correlation_key=latest.correlation_key,
        seen_at=NOW_UTC,
        safe_context=latest.safe_context,
    )

    assert changed == 0
    assert len(session.statements) == 2


async def test_mark_resolved_is_scoped_and_monotonic() -> None:
    session = RecordingSession(ScalarResult(None), SimpleNamespace(rowcount=1))

    changed = await ProductionInvariantAlertsRepo.mark_resolved(
        session,
        alert_type="paid_without_entitlement",
        correlation_key="paid_without_entitlement",
        resolved_at=NOW_UTC,
    )

    assert changed == 1
    sql = _compile(session.statements[1])
    assert "production_invariant_alerts.status = %(status_1)s" in sql
    assert "production_invariant_alerts.updated_at <= %(updated_at_1)s" in sql
    assert "last_seen_at=%(last_seen_at)s" in sql


def test_model_matches_existing_partial_unique_schema() -> None:
    table = cast(Any, ProductionInvariantAlert.__table__)
    indexes = {str(index.name): index for index in table.indexes}

    active_index = indexes["uq_production_invariant_alerts_active_type_key"]
    assert active_index.unique is True
    assert [column.name for column in active_index.columns] == ["type", "correlation_key"]
    assert str(active_index.dialect_options["postgresql"]["where"]) == "status = 'OPEN'"
