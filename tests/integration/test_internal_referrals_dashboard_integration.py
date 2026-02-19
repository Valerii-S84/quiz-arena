from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes import internal_referrals
from app.db.models.referrals import Referral
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.main import app

UTC = timezone.utc


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=70_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"R{uuid4().hex[:10].upper()}",
            username=None,
            first_name="ReferralDashboard",
            referred_by_user_id=None,
        )
        return user.id


async def _seed_referrals_dashboard_dataset(now_utc: datetime) -> tuple[int, int]:
    referrer_1 = await _create_user("ref-dashboard-referrer-1")
    referrer_2 = await _create_user("ref-dashboard-referrer-2")
    referred_ids = [await _create_user(f"ref-dashboard-referred-{idx}") for idx in range(1, 8)]

    async with SessionLocal.begin() as session:
        session.add_all(
            [
                Referral(
                    referrer_user_id=referrer_1,
                    referred_user_id=referred_ids[0],
                    referral_code="REF111",
                    status="STARTED",
                    qualified_at=None,
                    rewarded_at=None,
                    fraud_score=Decimal("0"),
                    created_at=now_utc - timedelta(hours=6),
                ),
                Referral(
                    referrer_user_id=referrer_1,
                    referred_user_id=referred_ids[1],
                    referral_code="REF111",
                    status="QUALIFIED",
                    qualified_at=now_utc - timedelta(hours=5),
                    rewarded_at=None,
                    fraud_score=Decimal("0"),
                    created_at=now_utc - timedelta(hours=6),
                ),
                Referral(
                    referrer_user_id=referrer_1,
                    referred_user_id=referred_ids[2],
                    referral_code="REF111",
                    status="REWARDED",
                    qualified_at=now_utc - timedelta(hours=8),
                    rewarded_at=now_utc - timedelta(hours=4),
                    fraud_score=Decimal("0"),
                    created_at=now_utc - timedelta(hours=9),
                ),
                Referral(
                    referrer_user_id=referrer_1,
                    referred_user_id=referred_ids[3],
                    referral_code="REF111",
                    status="REJECTED_FRAUD",
                    qualified_at=None,
                    rewarded_at=None,
                    fraud_score=Decimal("95.00"),
                    created_at=now_utc - timedelta(hours=3),
                ),
                Referral(
                    referrer_user_id=referrer_2,
                    referred_user_id=referred_ids[4],
                    referral_code="REF222",
                    status="REJECTED_FRAUD",
                    qualified_at=None,
                    rewarded_at=None,
                    fraud_score=Decimal("80.00"),
                    created_at=now_utc - timedelta(hours=2),
                ),
                Referral(
                    referrer_user_id=referrer_2,
                    referred_user_id=referred_ids[5],
                    referral_code="REF222",
                    status="CANCELED",
                    qualified_at=None,
                    rewarded_at=None,
                    fraud_score=Decimal("0"),
                    created_at=now_utc - timedelta(hours=2),
                ),
                Referral(
                    referrer_user_id=referrer_2,
                    referred_user_id=referred_ids[6],
                    referral_code="REF222",
                    status="DEFERRED_LIMIT",
                    qualified_at=now_utc - timedelta(hours=7),
                    rewarded_at=None,
                    fraud_score=Decimal("0"),
                    created_at=now_utc - timedelta(hours=7),
                ),
            ]
        )

    return referrer_1, referrer_2


@pytest.mark.asyncio
async def test_internal_referrals_dashboard_returns_funnel_and_fraud_triage_metrics(monkeypatch) -> None:
    now_utc = datetime.now(UTC)
    referrer_1, referrer_2 = await _seed_referrals_dashboard_dataset(now_utc)

    monkeypatch.setattr(
        internal_referrals,
        "get_settings",
        lambda: SimpleNamespace(
            internal_api_token="internal-secret",
            internal_api_allowlist="127.0.0.1/32",
            referrals_alert_min_started=1,
            referrals_alert_max_fraud_rejected_rate=0.20,
            referrals_alert_max_rejected_fraud_total=1,
            referrals_alert_max_referrer_rejected_fraud=1,
        ),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/internal/referrals/dashboard?window_hours=24",
            headers={"X-Internal-Token": "internal-secret"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["window_hours"] == 24
    assert payload["referrals_started_total"] == 7
    assert payload["qualified_like_total"] == 3
    assert payload["rewarded_total"] == 1
    assert payload["rejected_fraud_total"] == 2
    assert payload["canceled_total"] == 1
    assert payload["qualification_rate"] == pytest.approx(3 / 7)
    assert payload["reward_rate"] == pytest.approx(1 / 7)
    assert payload["fraud_rejected_rate"] == pytest.approx(2 / 7)
    assert payload["status_counts"] == {
        "STARTED": 1,
        "QUALIFIED": 1,
        "REWARDED": 1,
        "REJECTED_FRAUD": 2,
        "CANCELED": 1,
        "DEFERRED_LIMIT": 1,
    }

    assert len(payload["top_referrers"]) == 2
    assert payload["top_referrers"][0]["referrer_user_id"] == referrer_1
    assert payload["top_referrers"][0]["started_total"] == 4
    assert payload["top_referrers"][0]["rejected_fraud_total"] == 1
    assert payload["top_referrers"][0]["rejected_fraud_rate"] == pytest.approx(1 / 4)
    assert payload["top_referrers"][1]["referrer_user_id"] == referrer_2
    assert payload["top_referrers"][1]["started_total"] == 3
    assert payload["top_referrers"][1]["rejected_fraud_total"] == 1
    assert payload["top_referrers"][1]["rejected_fraud_rate"] == pytest.approx(1 / 3)

    assert len(payload["recent_fraud_cases"]) == 2
    assert payload["recent_fraud_cases"][0]["fraud_score"] == 80.0
    assert payload["recent_fraud_cases"][1]["fraud_score"] == 95.0

    assert payload["thresholds"] == {
        "min_started": 1,
        "max_fraud_rejected_rate": 0.2,
        "max_rejected_fraud_total": 1,
        "max_referrer_rejected_fraud": 1,
    }
    assert payload["alerts"] == {
        "thresholds_applied": True,
        "fraud_spike_detected": True,
        "fraud_rate_above_threshold": True,
        "rejected_fraud_total_above_threshold": True,
        "referrer_spike_detected": True,
    }
