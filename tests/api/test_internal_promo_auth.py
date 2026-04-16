from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import internal_promo, internal_promo_campaigns, internal_promo_helpers
from app.main import app
from app.services.internal_auth import OPS_UI_SESSION_COOKIE


def _settings(*, allowlist: str = "127.0.0.1/32") -> SimpleNamespace:
    return SimpleNamespace(
        internal_api_token="internal-secret",
        internal_api_allowlist=allowlist,
        internal_api_trusted_proxies="127.0.0.1/32",
    )


@asynccontextmanager
async def _empty_session():
    yield object()


def _trusted_headers(*, include_token: bool = False) -> dict[str, str]:
    headers = {"X-Forwarded-For": "127.0.0.1"}
    if include_token:
        headers["X-Internal-Token"] = "internal-secret"
    return headers


def test_internal_promo_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(internal_promo, "get_settings", lambda: _settings())

    client = TestClient(app)
    response = client.post(
        "/internal/promo/redeem",
        json={"user_id": 1, "promo_code": "TEST", "idempotency_key": "idem-1"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_internal_promo_rejects_disallowed_ip(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_promo, "get_settings", lambda: _settings(allowlist="192.168.0.0/16")
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


def test_internal_promo_campaigns_accept_machine_token(monkeypatch) -> None:
    async def _list_codes(session, *, status, campaign_name, limit):
        del session, status, campaign_name, limit
        return []

    monkeypatch.setattr(internal_promo, "get_settings", lambda: _settings())
    monkeypatch.setattr(internal_promo_campaigns.SessionLocal, "begin", _empty_session)
    monkeypatch.setattr(internal_promo_campaigns.PromoRepo, "list_codes", _list_codes)

    client = TestClient(app, client=("127.0.0.1", 5200))
    response = client.get("/internal/promo/campaigns", headers=_trusted_headers(include_token=True))

    assert response.status_code == 200
    assert response.json() == {"campaigns": []}


def test_internal_promo_campaigns_accept_ops_session_cookie(monkeypatch) -> None:
    async def _list_codes(session, *, status, campaign_name, limit):
        del session, status, campaign_name, limit
        return []

    async def _validate_ops_session(*, settings, session_id):
        del settings
        return session_id == "ops-session"

    monkeypatch.setattr(internal_promo, "get_settings", lambda: _settings())
    monkeypatch.setattr(internal_promo_campaigns.SessionLocal, "begin", _empty_session)
    monkeypatch.setattr(internal_promo_campaigns.PromoRepo, "list_codes", _list_codes)
    monkeypatch.setattr(internal_promo_helpers, "validate_ops_ui_session", _validate_ops_session)

    client = TestClient(app, client=("127.0.0.1", 5201))
    client.cookies.set(OPS_UI_SESSION_COOKIE, "ops-session")
    response = client.get("/internal/promo/campaigns", headers=_trusted_headers())

    assert response.status_code == 200
    assert response.json() == {"campaigns": []}


def test_internal_promo_redeem_rejects_ops_session_cookie(monkeypatch) -> None:
    async def _validate_ops_session(*, settings, session_id):
        del settings, session_id
        return True

    monkeypatch.setattr(internal_promo, "get_settings", lambda: _settings())
    monkeypatch.setattr(internal_promo_helpers, "validate_ops_ui_session", _validate_ops_session)

    client = TestClient(app, client=("127.0.0.1", 5202))
    client.cookies.set(OPS_UI_SESSION_COOKIE, "ops-session")
    response = client.post(
        "/internal/promo/redeem",
        json={"user_id": 1, "promo_code": "TEST", "idempotency_key": "idem-3"},
        headers=_trusted_headers(),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_internal_promo_dashboard_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(internal_promo, "get_settings", lambda: _settings())

    client = TestClient(app)
    response = client.get("/internal/promo/dashboard")

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_internal_promo_dashboard_rejects_disallowed_ip(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_promo, "get_settings", lambda: _settings(allowlist="192.168.0.0/16")
    )

    client = TestClient(app)
    response = client.get(
        "/internal/promo/dashboard",
        headers={
            "X-Internal-Token": "internal-secret",
            "X-Forwarded-For": "10.0.0.25",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_internal_promo_campaigns_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(internal_promo, "get_settings", lambda: _settings())

    client = TestClient(app)
    response = client.get("/internal/promo/campaigns")

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_internal_promo_refund_rollback_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(internal_promo, "get_settings", lambda: _settings())

    client = TestClient(app)
    response = client.post(
        "/internal/promo/refund-rollback",
        json={"purchase_id": "123e4567-e89b-12d3-a456-426614174000"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}
