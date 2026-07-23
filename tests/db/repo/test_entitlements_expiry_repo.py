from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from app.db.repo.entitlements_repo import EntitlementsRepo
from tests.db.repo._helpers import RecordingSession
from tests.type_helpers import ScalarResult, ScalarsResult

NOW_UTC = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def _compile(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


async def test_count_expired_active_premium_filters_effective_window() -> None:
    session = RecordingSession(ScalarResult(2))

    result = await EntitlementsRepo.count_expired_active_premium(session, now_utc=NOW_UTC)

    sql = _compile(session.statement)
    assert result == 2
    assert "entitlements.entitlement_type = %(entitlement_type_1)s" in sql
    assert "entitlements.status = %(status_1)s" in sql
    assert "entitlements.ends_at <= %(ends_at_1)s" in sql


async def test_expire_active_premium_before_updates_only_expired_active_rows() -> None:
    session = RecordingSession(
        ScalarsResult([10, 11]),
        SimpleNamespace(rowcount=2),
    )

    result = await EntitlementsRepo.expire_active_premium_before(
        session,
        now_utc=NOW_UTC,
        limit=100,
    )

    select_sql = _compile(session.statements[0])
    update_sql = _compile(session.statements[1])
    assert result == 2
    assert "FOR UPDATE SKIP LOCKED" in select_sql
    assert "UPDATE entitlements" in update_sql
    assert "entitlements.status = %(status_1)s" in update_sql
    assert "entitlements.ends_at <= %(ends_at_1)s" in update_sql


async def test_expire_active_premium_before_is_idempotent_when_empty() -> None:
    session = RecordingSession(ScalarsResult([]))

    result = await EntitlementsRepo.expire_active_premium_before(
        session,
        now_utc=NOW_UTC,
        limit=100,
    )

    assert result == 0
    assert len(session.statements) == 1
