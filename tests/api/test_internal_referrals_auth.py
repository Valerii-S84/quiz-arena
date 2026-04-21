from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import internal_referrals, internal_referrals_helpers, internal_referrals_queue
from app.main import app
from app.services.internal_auth import OPS_UI_SESSION_COOKIE


def _settings(*, allowlist: str = "127.0.0.1/32") -> SimpleNamespace:
    return SimpleNamespace(
        internal_api_token="internal-secret",
        internal_api_allowlist=allowlist,
        internal_api_trusted_proxies="127.0.0.1/32",
        referrals_alert_min_started=20,
        referrals_alert_max_fraud_rejected_rate=0.25,
        referrals_alert_max_rejected_fraud_total=10,
        referrals_alert_max_referrer_rejected_fraud=3,
    )


@asynccontextmanager
async def _empty_session():
    yield object()


def _trusted_headers() -> dict[str, str]:
    return {"X-Forwarded-For": "127.0.0.1"}


def test_internal_referrals_dashboard_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(internal_referrals, "get_settings", lambda: _settings())

    client = TestClient(app)
    response = client.get("/internal/referrals/dashboard")

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_internal_referrals_dashboard_rejects_disallowed_ip(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_referrals,
        "get_settings",
        lambda: _settings(allowlist="192.168.0.0/16"),
    )

    client = TestClient(app)
    response = client.get(
        "/internal/referrals/dashboard",
        headers={
            "X-Internal-Token": "internal-secret",
            "X-Forwarded-For": "10.0.0.25",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_internal_referrals_review_queue_accepts_ops_session_cookie(monkeypatch) -> None:
    async def _list_for_review_since(session, *, since_utc, status, limit):
        del session, since_utc, status, limit
        return []

    async def _validate_ops_session(*, settings, session_id):
        del settings
        return session_id == "ops-session"

    monkeypatch.setattr(internal_referrals, "get_settings", lambda: _settings())
    monkeypatch.setattr(internal_referrals_queue.SessionLocal, "begin", _empty_session)
    monkeypatch.setattr(
        internal_referrals_queue.ReferralsRepo,
        "list_for_review_since",
        _list_for_review_since,
    )
    monkeypatch.setattr(
        internal_referrals_helpers,
        "validate_ops_ui_session",
        _validate_ops_session,
    )

    client = TestClient(app, client=("127.0.0.1", 5300))
    client.cookies.set(OPS_UI_SESSION_COOKIE, "ops-session")
    response = client.get("/internal/referrals/review-queue", headers=_trusted_headers())

    assert response.status_code == 200
    assert response.json()["cases"] == []


def test_internal_referrals_review_queue_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(internal_referrals, "get_settings", lambda: _settings())

    client = TestClient(app)
    response = client.get("/internal/referrals/review-queue")

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_internal_referrals_review_action_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(internal_referrals, "get_settings", lambda: _settings())

    client = TestClient(app)
    response = client.post(
        "/internal/referrals/1/review",
        json={"decision": "CONFIRM_FRAUD"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_internal_referrals_events_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(internal_referrals, "get_settings", lambda: _settings())

    client = TestClient(app)
    response = client.get("/internal/referrals/events")

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}
