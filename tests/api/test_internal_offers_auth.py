from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import internal_offers
from app.main import app
from app.services.internal_auth import OPS_UI_SESSION_COOKIE


def _settings(*, allowlist: str = "127.0.0.1/32") -> SimpleNamespace:
    return SimpleNamespace(
        internal_api_token="internal-secret",
        internal_api_allowlist=allowlist,
        internal_api_trusted_proxies="127.0.0.1/32",
        offers_alert_min_impressions=50,
        offers_alert_min_conversion_rate=0.03,
        offers_alert_max_dismiss_rate=0.60,
        offers_alert_max_impressions_per_user=4.0,
    )


@asynccontextmanager
async def _empty_session():
    yield object()


def _snapshot() -> SimpleNamespace:
    return SimpleNamespace(
        generated_at=datetime.now(timezone.utc),
        window_hours=24,
        impressions_total=0,
        unique_users=0,
        clicks_total=0,
        dismissals_total=0,
        conversions_total=0,
        click_through_rate=0.0,
        conversion_rate=0.0,
        dismiss_rate=0.0,
        impressions_per_user=0.0,
        top_offer_codes={},
    )


def _alert_state() -> SimpleNamespace:
    return SimpleNamespace(
        thresholds_applied=True,
        conversion_drop_detected=False,
        spam_anomaly_detected=False,
        conversion_rate_below_threshold=False,
        dismiss_rate_above_threshold=False,
        impressions_per_user_above_threshold=False,
    )


def test_internal_offers_dashboard_accepts_machine_token(monkeypatch) -> None:
    async def _build_snapshot(session, *, now_utc, window_hours):
        del session, now_utc, window_hours
        return _snapshot()

    monkeypatch.setattr(internal_offers, "get_settings", lambda: _settings())
    monkeypatch.setattr(internal_offers.SessionLocal, "begin", _empty_session)
    monkeypatch.setattr(internal_offers, "build_offer_funnel_snapshot", _build_snapshot)
    monkeypatch.setattr(
        internal_offers,
        "get_offer_alert_thresholds",
        lambda settings: SimpleNamespace(
            min_impressions=settings.offers_alert_min_impressions,
            min_conversion_rate=settings.offers_alert_min_conversion_rate,
            max_dismiss_rate=settings.offers_alert_max_dismiss_rate,
            max_impressions_per_user=settings.offers_alert_max_impressions_per_user,
        ),
    )
    monkeypatch.setattr(
        internal_offers,
        "evaluate_offer_alert_state",
        lambda *, snapshot, thresholds: _alert_state(),
    )

    client = TestClient(app, client=("127.0.0.1", 5400))
    response = client.get(
        "/internal/offers/dashboard",
        headers={
            "X-Internal-Token": "internal-secret",
            "X-Forwarded-For": "127.0.0.1",
        },
    )

    assert response.status_code == 200
    assert response.json()["impressions_total"] == 0


def test_internal_offers_dashboard_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(internal_offers, "get_settings", lambda: _settings())

    client = TestClient(app)
    response = client.get("/internal/offers/dashboard")

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_internal_offers_dashboard_rejects_disallowed_ip(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_offers,
        "get_settings",
        lambda: _settings(allowlist="192.168.0.0/16"),
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


def test_internal_offers_dashboard_rejects_ops_session_cookie(monkeypatch) -> None:
    monkeypatch.setattr(internal_offers, "get_settings", lambda: _settings())

    client = TestClient(app, client=("127.0.0.1", 5401))
    client.cookies.set(OPS_UI_SESSION_COOKIE, "ops-session")
    response = client.get(
        "/internal/offers/dashboard",
        headers={"X-Forwarded-For": "127.0.0.1"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}
