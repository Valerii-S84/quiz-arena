from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import internal_referrals
from app.main import app


def test_internal_referrals_dashboard_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_referrals,
        "get_settings",
        lambda: SimpleNamespace(
            internal_api_token="internal-secret",
            internal_api_allowlist="127.0.0.1/32",
            referrals_alert_min_started=20,
            referrals_alert_max_fraud_rejected_rate=0.25,
            referrals_alert_max_rejected_fraud_total=10,
            referrals_alert_max_referrer_rejected_fraud=3,
        ),
    )

    client = TestClient(app)
    response = client.get("/internal/referrals/dashboard")

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_internal_referrals_dashboard_rejects_disallowed_ip(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_referrals,
        "get_settings",
        lambda: SimpleNamespace(
            internal_api_token="internal-secret",
            internal_api_allowlist="192.168.0.0/16",
            referrals_alert_min_started=20,
            referrals_alert_max_fraud_rejected_rate=0.25,
            referrals_alert_max_rejected_fraud_total=10,
            referrals_alert_max_referrer_rejected_fraud=3,
        ),
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


def test_internal_referrals_review_queue_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_referrals,
        "get_settings",
        lambda: SimpleNamespace(
            internal_api_token="internal-secret",
            internal_api_allowlist="127.0.0.1/32",
            referrals_alert_min_started=20,
            referrals_alert_max_fraud_rejected_rate=0.25,
            referrals_alert_max_rejected_fraud_total=10,
            referrals_alert_max_referrer_rejected_fraud=3,
        ),
    )

    client = TestClient(app)
    response = client.get("/internal/referrals/review-queue")

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_internal_referrals_review_action_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_referrals,
        "get_settings",
        lambda: SimpleNamespace(
            internal_api_token="internal-secret",
            internal_api_allowlist="127.0.0.1/32",
            referrals_alert_min_started=20,
            referrals_alert_max_fraud_rejected_rate=0.25,
            referrals_alert_max_rejected_fraud_total=10,
            referrals_alert_max_referrer_rejected_fraud=3,
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/internal/referrals/1/review",
        json={"decision": "CONFIRM_FRAUD"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


def test_internal_referrals_events_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(
        internal_referrals,
        "get_settings",
        lambda: SimpleNamespace(
            internal_api_token="internal-secret",
            internal_api_allowlist="127.0.0.1/32",
            referrals_alert_min_started=20,
            referrals_alert_max_fraud_rejected_rate=0.25,
            referrals_alert_max_rejected_fraud_total=10,
            referrals_alert_max_referrer_rejected_fraud=3,
        ),
    )

    client = TestClient(app)
    response = client.get("/internal/referrals/events")

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}
