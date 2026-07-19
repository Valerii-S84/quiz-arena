from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes.admin import deps as admin_deps
from app.api.routes.admin import overview
from app.main import app
from app.services.admin import cache as admin_cache
from tests.type_helpers import AsyncBeginContext, build_settings


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
        "user_language_distribution": [],
        "user_age_distribution": [],
        "user_gender_distribution": [],
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
            "user_language_distribution": [
                {"language": "de", "users": 4},
                {"language": "en", "users": 1},
            ],
            "user_age_distribution": [],
            "user_gender_distribution": [],
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
    assert response.json()["user_language_distribution"] == [
        {"language": "de", "users": 4},
        {"language": "en", "users": 1},
    ]
    assert stored[0]["key"] == "admin:overview:7"
