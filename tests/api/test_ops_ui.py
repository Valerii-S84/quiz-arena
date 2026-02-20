from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import ops_ui
from app.main import app


def test_ops_root_redirects_to_promo() -> None:
    client = TestClient(app)
    response = client.get("/ops", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/ops/promo"


def test_ops_promo_page_is_served_for_allowed_ip(monkeypatch) -> None:
    monkeypatch.setattr(
        ops_ui,
        "get_settings",
        lambda: SimpleNamespace(internal_api_allowlist="127.0.0.1/32"),
    )

    client = TestClient(app)
    response = client.get("/ops/promo", headers={"X-Forwarded-For": "127.0.0.1"})

    assert response.status_code == 200
    assert "Promo Ops Console" in response.text


def test_ops_page_rejects_disallowed_ip(monkeypatch) -> None:
    monkeypatch.setattr(
        ops_ui,
        "get_settings",
        lambda: SimpleNamespace(internal_api_allowlist="192.168.0.0/16"),
    )

    client = TestClient(app)
    response = client.get("/ops/referrals", headers={"X-Forwarded-For": "10.0.0.7"})

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}
