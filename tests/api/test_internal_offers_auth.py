from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import internal_offers
from app.main import app


def test_internal_offers_dashboard_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_offers,
        "get_settings",
        lambda: SimpleNamespace(
            internal_api_token="internal-secret",
            internal_api_allowlist="127.0.0.1/32",
            offers_alert_min_impressions=50,
            offers_alert_min_conversion_rate=0.03,
            offers_alert_max_dismiss_rate=0.60,
            offers_alert_max_impressions_per_user=4.0,
        ),
    )

    client = TestClient(app)
    response = client.get("/internal/offers/dashboard")

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_internal_offers_dashboard_rejects_disallowed_ip(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_offers,
        "get_settings",
        lambda: SimpleNamespace(
            internal_api_token="internal-secret",
            internal_api_allowlist="192.168.0.0/16",
            offers_alert_min_impressions=50,
            offers_alert_min_conversion_rate=0.03,
            offers_alert_max_dismiss_rate=0.60,
            offers_alert_max_impressions_per_user=4.0,
        ),
    )

    client = TestClient(app)
    response = client.get(
        "/internal/offers/dashboard",
        headers={
            "X-Internal-Token": "internal-secret",
            "X-Forwarded-For": "10.0.0.25",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}
