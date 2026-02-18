from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import internal_promo
from app.main import app


def test_internal_promo_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_promo,
        "get_settings",
        lambda: SimpleNamespace(
            internal_api_token="internal-secret",
            internal_api_allowlist="127.0.0.1/32",
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/internal/promo/redeem",
        json={"user_id": 1, "promo_code": "TEST", "idempotency_key": "idem-1"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_internal_promo_rejects_disallowed_ip(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_promo,
        "get_settings",
        lambda: SimpleNamespace(
            internal_api_token="internal-secret",
            internal_api_allowlist="192.168.0.0/16",
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/internal/promo/redeem",
        json={"user_id": 1, "promo_code": "TEST", "idempotency_key": "idem-2"},
        headers={
            "X-Internal-Token": "internal-secret",
            "X-Forwarded-For": "10.0.0.25",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}
