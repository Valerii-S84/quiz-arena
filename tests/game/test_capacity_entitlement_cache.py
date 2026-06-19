from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from app.db.repo.entitlements_repo import EntitlementsRepo, entitlement_request_cache
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import AsyncSessionStub
from tests.type_helpers import ScalarResult as _ScalarResult

UTC = timezone.utc


@pytest.mark.asyncio
async def test_entitlement_cache_is_scoped_by_user_and_keeps_missing_user_denied() -> None:
    now_utc = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)
    session = RecordingSession(_ScalarResult("premium_week"), _ScalarResult(None))

    with entitlement_request_cache():
        assert await EntitlementsRepo.has_active_premium(session, 7, now_utc) is True
        assert await EntitlementsRepo.get_active_premium_scope(session, 8, now_utc) is None
        assert (
            await EntitlementsRepo.get_active_premium_scope(session, 7, now_utc) == "premium_week"
        )
        assert await EntitlementsRepo.has_active_premium(session, 8, now_utc) is False

    active_sql = compile_statement(session.statements[0])
    assert "entitlements.starts_at <=" in active_sql
    assert "entitlements.ends_at IS NULL OR entitlements.ends_at >" in active_sql
    assert len(session.statements) == 2


@pytest.mark.asyncio
async def test_entitlement_cache_does_not_reuse_missing_status_across_flows() -> None:
    now_utc = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)
    session = RecordingSession(_ScalarResult(None), _ScalarResult("premium_month"))

    with entitlement_request_cache():
        assert await EntitlementsRepo.has_active_premium(session, 7, now_utc) is False

    with entitlement_request_cache():
        assert await EntitlementsRepo.has_active_premium(session, 7, now_utc) is True

    assert len(session.statements) == 2


@pytest.mark.asyncio
async def test_entitlement_cache_does_not_store_failed_lookup() -> None:
    now_utc = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)
    session = _FailThenScopeSession()

    with entitlement_request_cache():
        with pytest.raises(RuntimeError, match="transient entitlement lookup failure"):
            await EntitlementsRepo.has_active_premium(session, 7, now_utc)

        assert await EntitlementsRepo.get_active_premium_scope(session, 7, now_utc) == "premium_day"

    assert session.execute_calls == 2


class _FailThenScopeSession(AsyncSessionStub):
    def __init__(self) -> None:
        self.execute_calls = 0

    async def execute(
        self,
        statement: Any,
        params: Any = None,
        *,
        execution_options: Any = None,
        bind_arguments: Any = None,
        _parent_execute_state: Any = None,
        _add_event: Any = None,
    ) -> Any:
        del statement, params, execution_options, bind_arguments, _parent_execute_state, _add_event
        self.execute_calls += 1
        if self.execute_calls == 1:
            raise RuntimeError("transient entitlement lookup failure")
        return _ScalarResult("premium_day")
