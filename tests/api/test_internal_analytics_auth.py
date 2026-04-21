from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import internal_analytics
from app.main import app
from app.services.internal_auth import OPS_UI_SESSION_COOKIE


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        internal_api_token="internal-secret",
        internal_api_allowlist="127.0.0.1/32",
        internal_api_trusted_proxies="127.0.0.1/32",
    )


def test_internal_analytics_dashboard_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(internal_analytics, "get_settings", lambda: _settings())

    client = TestClient(app)
    response = client.get("/internal/analytics/executive")

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_internal_analytics_dashboard_rejects_ops_session_cookie(monkeypatch) -> None:
    monkeypatch.setattr(internal_analytics, "get_settings", lambda: _settings())

    client = TestClient(app, client=("127.0.0.1", 5500))
    client.cookies.set(OPS_UI_SESSION_COOKIE, "ops-session")
    response = client.get(
        "/internal/analytics/executive",
        headers={"X-Forwarded-For": "127.0.0.1"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}
