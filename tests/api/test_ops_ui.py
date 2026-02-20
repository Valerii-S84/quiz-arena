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
        lambda: SimpleNamespace(
            internal_api_allowlist="127.0.0.1/32",
            internal_api_trusted_proxies="127.0.0.1/32",
        ),
    )

    client = TestClient(app, client=("127.0.0.1", 5100))
    response = client.get("/ops/promo", headers={"X-Forwarded-For": "127.0.0.1"})

    assert response.status_code == 200
    assert "Promo Ops Console" in response.text


def test_ops_page_rejects_disallowed_ip(monkeypatch) -> None:
    monkeypatch.setattr(
        ops_ui,
        "get_settings",
        lambda: SimpleNamespace(
            internal_api_allowlist="192.168.0.0/16",
            internal_api_trusted_proxies="127.0.0.1/32",
        ),
    )

    client = TestClient(app, client=("127.0.0.1", 5101))
    response = client.get("/ops/referrals", headers={"X-Forwarded-For": "10.0.0.7"})

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_ops_page_rejects_spoofed_forwarded_for_from_untrusted_proxy(monkeypatch) -> None:
    monkeypatch.setattr(
        ops_ui,
        "get_settings",
        lambda: SimpleNamespace(
            internal_api_allowlist="10.0.0.0/8",
            internal_api_trusted_proxies="127.0.0.1/32",
        ),
    )

    client = TestClient(app, client=("198.51.100.10", 5102))
    response = client.get("/ops/referrals", headers={"X-Forwarded-For": "10.0.0.7"})

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}
