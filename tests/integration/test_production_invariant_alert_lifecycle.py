from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.db.models.production_reliability import ProductionInvariantAlert
from app.db.repo.production_invariant_alerts_repo import ProductionInvariantAlertsRepo
from app.db.session import SessionLocal
from app.services.production_invariants import run_checks_in_session

BASE_TIME = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


async def test_alert_lifecycle_preserves_resolved_episode_history() -> None:
    alert_type = "integration_alert_episode_history"
    correlation_key = "integration:episode-history"
    await _clear(alert_type, correlation_key)
    try:
        assert await _record_failure(alert_type, correlation_key, BASE_TIME) == 1
        assert (
            await _record_failure(
                alert_type,
                correlation_key,
                BASE_TIME + timedelta(minutes=1),
            )
            == 1
        )
        assert (
            await _resolve(
                alert_type,
                correlation_key,
                BASE_TIME + timedelta(minutes=2),
            )
            == 1
        )
        assert (
            await _record_failure(
                alert_type,
                correlation_key,
                BASE_TIME + timedelta(minutes=3),
            )
            == 1
        )

        alerts = await _load_all(alert_type, correlation_key)
        assert [(alert.status, alert.count) for alert in alerts] == [
            ("RESOLVED", 2),
            ("OPEN", 1),
        ]
    finally:
        await _clear(alert_type, correlation_key)


async def test_older_failure_cannot_reopen_after_newer_resolution() -> None:
    alert_type = "integration_alert_monotonic"
    correlation_key = "integration:monotonic"
    await _clear(alert_type, correlation_key)
    try:
        assert await _record_failure(alert_type, correlation_key, BASE_TIME) == 1
        assert (
            await _resolve(
                alert_type,
                correlation_key,
                BASE_TIME + timedelta(minutes=2),
            )
            == 1
        )
        assert (
            await _record_failure(
                alert_type,
                correlation_key,
                BASE_TIME + timedelta(minutes=1),
            )
            == 0
        )

        alerts = await _load_all(alert_type, correlation_key)
        assert len(alerts) == 1
        assert alerts[0].status == "RESOLVED"
        assert alerts[0].updated_at == BASE_TIME + timedelta(minutes=2)
    finally:
        await _clear(alert_type, correlation_key)


async def test_all_invariant_queries_execute_against_current_schema() -> None:
    async with SessionLocal() as session:
        results = await run_checks_in_session(
            session,
            now_utc=BASE_TIME,
            heartbeat_registry=(),
        )
        await session.rollback()

    assert results
    assert {result.name for result in results} >= {
        "daily_cup_cancel_message_gap",
        "private_tournament_round_delivery_gap",
        "telegram_delivery_pending_stale",
    }


async def _record_failure(alert_type: str, correlation_key: str, seen_at: datetime) -> int:
    async with SessionLocal.begin() as session:
        return await ProductionInvariantAlertsRepo.record_open(
            session,
            severity="P1",
            alert_type=alert_type,
            correlation_key=correlation_key,
            seen_at=seen_at,
            safe_context={"check_name": alert_type},
        )


async def _resolve(alert_type: str, correlation_key: str, resolved_at: datetime) -> int:
    async with SessionLocal.begin() as session:
        return await ProductionInvariantAlertsRepo.mark_resolved(
            session,
            alert_type=alert_type,
            correlation_key=correlation_key,
            resolved_at=resolved_at,
        )


async def _load_all(
    alert_type: str,
    correlation_key: str,
) -> list[ProductionInvariantAlert]:
    async with SessionLocal() as session:
        result = await session.scalars(
            select(ProductionInvariantAlert)
            .where(
                ProductionInvariantAlert.type == alert_type,
                ProductionInvariantAlert.correlation_key == correlation_key,
            )
            .order_by(ProductionInvariantAlert.id)
        )
        return list(result.all())


async def _clear(alert_type: str, correlation_key: str) -> None:
    async with SessionLocal.begin() as session:
        await session.execute(
            delete(ProductionInvariantAlert).where(
                ProductionInvariantAlert.type == alert_type,
                ProductionInvariantAlert.correlation_key == correlation_key,
            )
        )
