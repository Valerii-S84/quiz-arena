from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.db.models.entitlements import Entitlement
from app.db.repo.entitlements_repo import EntitlementsRepo, entitlement_request_cache
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult

UTC = timezone.utc


class _PremiumStatusResult:
    def __init__(self, row: tuple[int, str | None] | None) -> None:
        self._row = row

    def one_or_none(self) -> tuple[int, str | None] | None:
        return self._row


def _entitlement(**overrides: object) -> Entitlement:
    now_utc = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    payload: dict[str, object] = {
        "id": 10,
        "user_id": 7,
        "entitlement_type": "PREMIUM",
        "scope": "daily_arena",
        "status": "ACTIVE",
        "starts_at": now_utc - timedelta(days=1),
        "ends_at": now_utc + timedelta(days=1),
        "source_purchase_id": uuid4(),
        "idempotency_key": "entitlement:test",
        "metadata_": {},
        "created_at": now_utc,
        "updated_at": now_utc,
    }
    payload.update(overrides)
    return Entitlement(**payload)


async def test_active_premium_queries_return_bool_scope_and_lock() -> None:
    now_utc = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    entitlement = _entitlement()

    active_session = RecordingSession(_PremiumStatusResult((entitlement.id, entitlement.scope)))
    assert await EntitlementsRepo.has_active_premium(active_session, 7, now_utc) is True
    active_sql = compile_statement(active_session.statement)
    assert "entitlements.user_id = 7" in active_sql
    assert "entitlements.entitlement_type = 'PREMIUM'" in active_sql
    assert "entitlements.status = 'ACTIVE'" in active_sql

    scope_session = RecordingSession(_PremiumStatusResult((entitlement.id, entitlement.scope)))
    assert (
        await EntitlementsRepo.get_active_premium_scope(scope_session, 7, now_utc) == "daily_arena"
    )

    missing_session = RecordingSession(_PremiumStatusResult(None))
    assert await EntitlementsRepo.get_active_premium_scope(missing_session, 7, now_utc) is None

    lock_session = RecordingSession(_ScalarResult(entitlement))
    assert (
        await EntitlementsRepo.get_active_premium_for_update(lock_session, 7, now_utc)
        is entitlement
    )
    assert "FOR UPDATE" in compile_statement(lock_session.statement)


async def test_entitlement_request_cache_reuses_premium_status_for_same_flow() -> None:
    now_utc = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    entitlement = _entitlement(scope="arena_plus")
    session = RecordingSession(_PremiumStatusResult((entitlement.id, entitlement.scope)))

    with entitlement_request_cache():
        assert await EntitlementsRepo.has_active_premium(session, 7, now_utc) is True
        assert await EntitlementsRepo.get_active_premium_scope(session, 7, now_utc) == "arena_plus"

    assert len(session.statements) == 1


async def test_active_premium_status_preserves_null_scope_rows() -> None:
    now_utc = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    entitlement = _entitlement(scope=None)
    session = RecordingSession(_PremiumStatusResult((entitlement.id, entitlement.scope)))

    with entitlement_request_cache():
        assert await EntitlementsRepo.has_active_premium(session, 7, now_utc) is True
        assert await EntitlementsRepo.get_active_premium_scope(session, 7, now_utc) is None

    assert len(session.statements) == 1


async def test_entitlement_request_cache_reuses_missing_status_for_same_flow() -> None:
    now_utc = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    session = RecordingSession(_PremiumStatusResult(None))

    with entitlement_request_cache():
        assert await EntitlementsRepo.has_active_premium(session, 7, now_utc) is False
        assert await EntitlementsRepo.get_active_premium_scope(session, 7, now_utc) is None

    assert len(session.statements) == 1


async def test_premium_window_queries_and_purchase_revoke_paths() -> None:
    now_utc = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    purchase_id = uuid4()

    recent_session = RecordingSession(_ScalarResult(10))
    assert (
        await EntitlementsRepo.has_recently_ended_premium_scope(
            recent_session,
            user_id=7,
            scope="daily_arena",
            since_utc=now_utc - timedelta(days=1),
            until_utc=now_utc,
        )
        is True
    )
    recent_sql = compile_statement(recent_session.statement)
    assert "entitlements.status != 'REVOKED'" in recent_sql
    assert "entitlements.ends_at IS NOT NULL" in recent_sql

    ending_session = RecordingSession(_ScalarResult(None))
    assert (
        await EntitlementsRepo.has_active_premium_scope_ending_within(
            ending_session,
            user_id=7,
            scope="daily_arena",
            now_utc=now_utc,
            until_utc=now_utc + timedelta(hours=1),
        )
        is False
    )

    active = _entitlement(id=11, source_purchase_id=purchase_id)
    scheduled = _entitlement(id=12, status="SCHEDULED", source_purchase_id=purchase_id)
    revoke_session = RecordingSession(_ScalarsResult([active, scheduled]))
    assert (
        await EntitlementsRepo.revoke_active_or_scheduled_by_purchase(
            revoke_session,
            purchase_id=purchase_id,
            now_utc=now_utc,
        )
        == 2
    )
    assert [active.status, scheduled.status] == ["REVOKED", "REVOKED"]
    assert revoke_session.flushed is True
