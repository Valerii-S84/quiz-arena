from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import internal_analytics
from app.main import app


def test_internal_analytics_dashboard_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_analytics,
        "get_settings",
        lambda: SimpleNamespace(
            internal_api_token="internal-secret",
            internal_api_allowlist="127.0.0.1/32",
        ),
    )

    client = TestClient(app)
    response = client.get("/internal/analytics/executive")

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}
