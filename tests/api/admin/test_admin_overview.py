from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes.admin import deps as admin_deps
from app.api.routes.admin import (
    overview,
    overview_activity_metrics,
    overview_metrics,
    overview_queries,
    overview_streak_metrics,
)
from app.main import app
from app.services.admin import cache as admin_cache
from tests.type_helpers import AsyncBeginContext, AsyncSessionStub
from tests.type_helpers import RowsResult as _RowsResult
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import build_settings


class _SessionWithExec(AsyncSessionStub):
    def __init__(self, *results) -> None:
        self._results = list(results)

    async def execute(self, stmt):
        del stmt
        return self._results.pop(0)


def _session_local(session: object) -> SimpleNamespace:
    return SimpleNamespace(begin=lambda: AsyncBeginContext(session))


def _settings():
    return build_settings(redis_url="redis://test")


def _admin() -> admin_deps.AdminPrincipal:
    return admin_deps.AdminPrincipal(
        id=uuid4(),
        email="admin@example.com",
        role="admin",
        two_factor_verified=True,
        client_ip="127.0.0.1",
    )


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_overview_metrics_helpers_compute_expected_values() -> None:
    assert overview_metrics.build_kpi(current=10.0, previous=5.0) == {
        "current": 10.0,
        "previous": 5.0,
        "delta_pct": 100.0,
    }
    assert overview_metrics.build_kpi(current=0.0, previous=0.0)["delta_pct"] == 0.0

    session = _SessionWithExec(
        _ScalarResult(11),
        _ScalarResult(7),
        _ScalarResult(3),
        _ScalarResult(99),
        _ScalarResult(5),
        _ScalarResult(2),
    )
    now_utc = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

    assert (
        await overview_activity_metrics.count_distinct_users(
            session,
            from_utc=now_utc,
            to_utc=now_utc,
        )
        == 11
    )
    assert (
        await overview_metrics.count_purchase_users(session, from_utc=now_utc, to_utc=now_utc) == 7
    )
    assert (
        await overview_metrics.count_first_purchase_users(session, from_utc=now_utc, to_utc=now_utc)
        == 3
    )
    assert await overview_metrics.sum_revenue_stars(session, from_utc=now_utc, to_utc=now_utc) == 99
    assert (
        await overview_metrics.count_distinct_event_users(
            session,
            event_type="bot_start_pressed",
            from_utc=now_utc,
            to_utc=now_utc,
        )
        == 5
    )
    assert (
        await overview_streak_metrics.count_users_reaching_streak_threshold(
            session,
            from_utc=now_utc,
            to_utc=now_utc,
            threshold=3,
        )
        == 2
    )


@pytest.mark.asyncio
async def test_retention_day_rate_handles_eligible_users_and_empty_cohorts() -> None:
    now_utc = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
    created_at = datetime(2026, 3, 3, 9, 0, tzinfo=UTC)
    session = _SessionWithExec(
        _RowsResult([(101, created_at), (202, created_at)]),
        _RowsResult([(101, date(2026, 3, 4)), (202, date(2026, 3, 5))]),
    )
    rate = await overview_activity_metrics.retention_day_rate(
        session,
        from_utc=datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
        to_utc=now_utc,
        day_offset=1,
    )
    assert rate == 50.0

    assert (
        await overview_activity_metrics.retention_day_rate(
            _SessionWithExec(_RowsResult([])),
            from_utc=datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
            to_utc=now_utc,
            day_offset=7,
        )
        == 0.0
    )


@pytest.mark.asyncio
async def test_retention_day_rate_returns_zero_when_target_by_user_becomes_empty() -> None:
    session = _SessionWithExec(
        _RowsResult([(101, datetime(2026, 3, 9, 9, 0, tzinfo=UTC))]),
    )

    rate = await overview_activity_metrics.retention_day_rate(
        session,
        from_utc=datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
        to_utc=datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
        day_offset=30,
    )

    assert rate == 0.0
    assert session._results == []


@pytest.mark.asyncio
async def test_retention_day_rate_ignores_event_rows_with_missing_user_id() -> None:
    session = _SessionWithExec(
        _RowsResult([(101, datetime(2026, 3, 3, 9, 0, tzinfo=UTC))]),
        _RowsResult([(None, date(2026, 3, 4))]),
    )

    rate = await overview_activity_metrics.retention_day_rate(
        session,
        from_utc=datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
        to_utc=datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
        day_offset=1,
    )

    assert rate == 0.0


@pytest.mark.skip(
    reason="line 140 is unreachable: after `if not target_by_user: return 0.0`, `base = len(target_by_user)` is always > 0"
)
def test_retention_day_rate_base_guard_is_unreachable() -> None:
    pass


@pytest.mark.asyncio
async def test_build_overview_payload_builds_kpis_and_alerts() -> None:
    session = _SessionWithExec(
        _ScalarResult(100),
        _ScalarResult(80),
        _ScalarResult(500),
        _ScalarResult(480),
        _ScalarResult(1000),
        _ScalarResult(900),
        _ScalarResult(20),
        _ScalarResult(10),
        _RowsResult([]),
        _RowsResult([]),
        _RowsResult([]),
        _RowsResult([]),
        _ScalarResult(200),
        _ScalarResult(100),
        _ScalarResult(7),
        _ScalarResult(4),
        _ScalarResult(20),
        _ScalarResult(10),
        _ScalarResult(5),
        _ScalarResult(5),
        _ScalarResult(3),
        _ScalarResult(5),
        _ScalarResult(10),
        _ScalarResult(7),
        _RowsResult([]),
        _RowsResult([]),
        _RowsResult([]),
        _RowsResult([(10, 2), (11, 3)]),
        _RowsResult([]),
        _ScalarResult(10),
        _ScalarResult(5),
        _ScalarResult(5),
        _ScalarResult(5),
        _ScalarResult(4),
        _ScalarResult(2),
        _ScalarResult(3),
        _ScalarResult(1),
        _ScalarResult(2),
        _ScalarResult(1),
        _ScalarResult(3),
        _ScalarResult(30),
    )
    now_utc = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
    payload = overview.OverviewResponse.model_validate(
        await overview_queries.build_overview_payload(session, now_utc=now_utc, days=7)
    )

    assert payload.period == "7d"
    assert payload.kpis["dau"].current == 100.0
    assert payload.kpis["start_users"].current == 20.0
    assert payload.kpis["conversion_start_to_quiz"].current == 35.0
    assert payload.kpis["revenue_eur"].current == float(
        Decimal(200) * overview_metrics.STAR_TO_EUR_RATE
    )
    assert payload.feature_usage["duel_created_users"].current == 10.0
    assert payload.hourly_activity_series[10] == {"hour": 10, "active_users": 2}
    assert payload.hourly_activity_series[11] == {"hour": 11, "active_users": 3}
    assert payload.hourly_activity_series[12] == {"hour": 12, "active_users": 0}
    assert payload.funnel[1] == {"step": "First Quiz", "value": 7}
    assert payload.funnel[2] == {"step": "Streak 3+", "value": 7}
    assert payload.funnel[3] == {"step": "Purchase", "value": 3}
    assert [str(item["type"]) for item in payload.alerts] == [
        "webhook_errors",
        "conversion_drop",
        "suspicious_activity",
    ]


@pytest.mark.asyncio
async def test_admin_cache_service_handles_success_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RedisClient:
        def __init__(self) -> None:
            self.payload = '{"ok":true}'
            self.set_calls: list[tuple[str, str, int]] = []

        async def ping(self) -> None:
            return None

        async def get(self, key: str) -> str:
            assert key == "cache-key"
            return self.payload

        async def set(self, key: str, value: str, ex: int) -> None:
            self.set_calls.append((key, value, ex))

    client = _RedisClient()
    monkeypatch.setattr(admin_cache, "_redis_client", None)
    monkeypatch.setattr(admin_cache.redis, "from_url", lambda *args, **kwargs: client)

    resolved = await admin_cache.get_redis_client(_settings())
    cached = await admin_cache.get_json_cache(settings=_settings(), key="cache-key")
    await admin_cache.set_json_cache(
        settings=_settings(), key="cache-key", value={"v": 1}, ttl_seconds=5
    )

    assert resolved is client
    assert cached == {"ok": True}
    assert client.set_calls == [("cache-key", '{"v":1}', 5)]

    monkeypatch.setattr(admin_cache, "_redis_client", None)

    class _BrokenRedisClient:
        async def ping(self) -> None:
            raise RuntimeError("no redis")

    monkeypatch.setattr(admin_cache.redis, "from_url", lambda *args, **kwargs: _BrokenRedisClient())
    assert await admin_cache.get_redis_client(_settings()) is None


def test_admin_overview_route_uses_cache_hit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {
        "period": "30d",
        "generated_at": "2026-03-10T12:00:00+00:00",
        "kpis": {"dau": {"current": 1.0, "previous": 0.0, "delta_pct": 100.0}},
        "revenue_series": [],
        "users_series": [],
        "funnel": [],
        "top_products": [],
        "feature_usage": {},
        "alerts": [],
    }
    app.dependency_overrides[overview.get_settings] = _settings
    app.dependency_overrides[admin_deps.get_current_admin] = _admin

    async def _cached(**kwargs):
        del kwargs
        return payload

    async def _unexpected_build(*args, **kwargs):
        del args, kwargs
        raise AssertionError("build_overview_payload should not run on cache hit")

    monkeypatch.setattr(overview, "get_json_cache", _cached)
    monkeypatch.setattr(overview, "build_overview_payload", _unexpected_build)

    response = client.get("/admin/overview?period=30d")

    assert response.status_code == 200
    assert response.json()["period"] == "30d"


def test_admin_overview_route_builds_payload_and_stores_cache(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored: list[dict[str, object]] = []
    session = object()
    app.dependency_overrides[overview.get_settings] = _settings
    app.dependency_overrides[admin_deps.get_current_admin] = _admin

    async def _miss(**kwargs):
        del kwargs
        return None

    async def _build(*args, **kwargs):
        del args, kwargs
        return {
            "period": "7d",
            "generated_at": datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
            "kpis": {"dau": {"current": 2.0, "previous": 1.0, "delta_pct": 100.0}},
            "revenue_series": [],
            "users_series": [],
            "funnel": [],
            "top_products": [],
            "feature_usage": {},
            "alerts": [],
        }

    async def _store(**kwargs):
        stored.append(kwargs)

    monkeypatch.setattr(overview, "SessionLocal", _session_local(session))
    monkeypatch.setattr(overview, "get_json_cache", _miss)
    monkeypatch.setattr(overview, "build_overview_payload", _build)
    monkeypatch.setattr(overview, "set_json_cache", _store)

    response = client.get("/admin/overview?period=unknown")

    assert response.status_code == 200
    assert response.json()["period"] == "7d"
    assert stored[0]["key"] == "admin:overview:7"
