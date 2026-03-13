from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes.admin import deps as admin_deps
from app.api.routes.admin import system
from app.main import app


class _RowsResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return list(self._rows)


class _ScalarResult:
    def __init__(self, value) -> None:
        self._value = value

    def scalar_one(self):
        return self._value


class _Session:
    def __init__(self, *results) -> None:
        self.results = list(results)

    async def execute(self, stmt):
        del stmt
        return self.results.pop(0)


class _AsyncBeginContext:
    def __init__(self, session: object) -> None:
        self._session = session

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def _session_local(*sessions: object) -> SimpleNamespace:
    remaining = list(sessions)
    return SimpleNamespace(begin=lambda: _AsyncBeginContext(remaining.pop(0)))


def _admin() -> admin_deps.AdminPrincipal:
    return admin_deps.AdminPrincipal(
        id=uuid4(),
        email="admin@example.com",
        role="admin",
        two_factor_verified=True,
        client_ip="127.0.0.1",
    )


def _settings() -> SimpleNamespace:
    return SimpleNamespace(redis_url="redis://test")


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides.clear()
    app.dependency_overrides[admin_deps.get_current_admin] = _admin
    app.dependency_overrides[system.get_settings] = _settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_system_service_status_handles_celery_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "SessionLocal", _session_local(_Session(_RowsResult([]), _ScalarResult(0))))
    monkeypatch.setattr(system, "get_redis_client", lambda settings: system.get_redis_client.__class__(None))

    async def _no_redis(settings):
        del settings
        return None

    monkeypatch.setattr(system, "get_redis_client", _no_redis)
    monkeypatch.setattr(system.celery_app.control, "inspect", lambda timeout=1.0: (_ for _ in ()).throw(RuntimeError("boom")))

    status = await system._service_status(settings=_settings())

    assert status["postgresql"] == {"ok": True}
    assert status["redis"] == {"ok": False}
    assert status["celery"] == {"ok": False, "workers": []}


def test_system_helpers_and_route_return_health_payload(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _RedisClient:
        async def llen(self, key: str) -> int:
            return {"q_high": 1, "q_normal": 2, "q_low": 3, "celery": 4}[key]

    assert system._percentile([], 0.5) is None
    assert system._percentile([1.0, 3.0, 2.0], 0.5) == 2.0

    monkeypatch.setattr(
        system,
        "SessionLocal",
        _session_local(
            _Session(_RowsResult([]), _ScalarResult(5)),
            _Session(
                _RowsResult([("worker_error", 7)]),
                _RowsResult([("email", "FAILED", datetime(2026, 3, 1, 12, 0, tzinfo=UTC))]),
                _RowsResult(
                    [
                        (datetime(2026, 3, 1, 10, 0, tzinfo=UTC), {"latency_ms": 50}),
                        (datetime(2026, 3, 1, 11, 0, tzinfo=UTC), {"latency_ms": 120}),
                    ]
                ),
            ),
        ),
    )

    async def _redis(settings):
        del settings
        return _RedisClient()

    monkeypatch.setattr(system, "get_redis_client", _redis)
    monkeypatch.setattr(
        system.celery_app.control,
        "inspect",
        lambda timeout=1.0: SimpleNamespace(ping=lambda: {"worker@1": {"ok": "pong"}}),
    )

    response = client.get("/admin/system")

    assert response.status_code == 200
    payload = response.json()
    assert payload["services"]["postgresql"] == {"ok": True}
    assert payload["services"]["bot_webhook"]["processed_updates_15m"] == 5
    assert payload["services"]["celery"]["workers"] == ["worker@1"]
    assert payload["queue_stats"] == {"pending": 6, "failed": 4}
    assert payload["top_10_errors"] == [{"type": "worker_error", "count": 7}]
    assert payload["api_latency"][0]["p95"] == 120.0


def test_system_route_handles_missing_redis_and_invalid_latency_payloads(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        system,
        "SessionLocal",
        _session_local(
            _Session(_RowsResult([]), _ScalarResult(0)),
            _Session(
                _RowsResult([]),
                _RowsResult([]),
                _RowsResult(
                    [
                        (datetime(2026, 3, 1, 10, 0, tzinfo=UTC), "broken"),
                        (datetime(2026, 3, 1, 11, 0, tzinfo=UTC), {}),
                        (datetime(2026, 3, 1, 12, 0, tzinfo=UTC), {"latency_ms": "slow"}),
                    ]
                ),
            ),
        ),
    )

    async def _no_redis(settings):
        del settings
        return None

    monkeypatch.setattr(system, "get_redis_client", _no_redis)
    monkeypatch.setattr(system.celery_app.control, "inspect", lambda timeout=1.0: None)

    response = client.get("/admin/system")

    assert response.status_code == 200
    payload = response.json()
    assert payload["services"]["bot_webhook"] == {"ok": False, "processed_updates_15m": 0}
    assert payload["services"]["redis"] == {"ok": False}
    assert payload["services"]["celery"] == {"ok": False, "workers": []}
    assert payload["queue_stats"] == {"pending": 0, "failed": 0}
    assert payload["api_latency"] == []
