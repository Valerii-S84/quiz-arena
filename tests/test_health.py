from fastapi.testclient import TestClient

from app.api.routes import health as health_routes
from app.main import app


async def _ok_check() -> dict[str, str]:
    return {"status": "ok"}


def test_health_ok(monkeypatch) -> None:
    monkeypatch.setattr(health_routes, "_check_database", _ok_check)
    monkeypatch.setattr(health_routes, "_check_redis", _ok_check)
    monkeypatch.setattr(health_routes, "_check_celery_worker", _ok_check)

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {
            "database": {"status": "ok"},
            "redis": {"status": "ok"},
            "celery": {"status": "ok"},
        },
    }


def test_health_returns_503_when_dependency_failed(monkeypatch) -> None:
    async def _failed_redis() -> dict[str, str]:
        return {"status": "failed", "error": "redis down"}

    monkeypatch.setattr(health_routes, "_check_database", _ok_check)
    monkeypatch.setattr(health_routes, "_check_redis", _failed_redis)
    monkeypatch.setattr(health_routes, "_check_celery_worker", _ok_check)

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["checks"]["redis"]["status"] == "failed"
    assert payload["checks"]["redis"]["error"] == "redis down"


def test_ready_ok(monkeypatch) -> None:
    monkeypatch.setattr(health_routes, "_check_database", _ok_check)
    monkeypatch.setattr(health_routes, "_check_redis", _ok_check)

    client = TestClient(app)
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {
            "database": {"status": "ok"},
            "redis": {"status": "ok"},
        },
    }


def test_ready_stays_200_when_celery_failed(monkeypatch) -> None:
    async def _failed_celery() -> dict[str, str]:
        return {"status": "failed", "error": "worker not responding"}

    monkeypatch.setattr(health_routes, "_check_database", _ok_check)
    monkeypatch.setattr(health_routes, "_check_redis", _ok_check)
    monkeypatch.setattr(health_routes, "_check_celery_worker", _failed_celery)

    client = TestClient(app)
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {
            "database": {"status": "ok"},
            "redis": {"status": "ok"},
        },
    }
