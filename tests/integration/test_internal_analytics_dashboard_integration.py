from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.db.models.analytics_daily import AnalyticsDaily
from app.db.session import SessionLocal
from app.main import app

UTC = timezone.utc


@pytest.mark.asyncio
async def test_internal_analytics_executive_returns_latest_rows_desc() -> None:
    now_utc = datetime.now(UTC)
    async with SessionLocal.begin() as session:
        session.add_all(
            [
                AnalyticsDaily(
                    local_date_berlin=date(2026, 2, 19),
                    dau=12,
                    wau=50,
                    mau=140,
                    purchases_credited_total=5,
                    purchasers_total=4,
                    purchase_rate=Decimal("0.333333"),
                    promo_redemptions_total=8,
                    promo_redemptions_applied_total=4,
                    promo_redemption_rate=Decimal("0.5"),
                    promo_to_paid_conversions_total=2,
                    quiz_sessions_started_total=70,
                    quiz_sessions_completed_total=56,
                    gameplay_completion_rate=Decimal("0.8"),
                    energy_zero_events_total=6,
                    streak_lost_events_total=2,
                    referral_reward_milestone_events_total=1,
                    referral_reward_granted_events_total=1,
                    calculated_at=now_utc,
                ),
                AnalyticsDaily(
                    local_date_berlin=date(2026, 2, 18),
                    dau=10,
                    wau=46,
                    mau=132,
                    purchases_credited_total=3,
                    purchasers_total=2,
                    purchase_rate=Decimal("0.2"),
                    promo_redemptions_total=5,
                    promo_redemptions_applied_total=2,
                    promo_redemption_rate=Decimal("0.4"),
                    promo_to_paid_conversions_total=1,
                    quiz_sessions_started_total=64,
                    quiz_sessions_completed_total=48,
                    gameplay_completion_rate=Decimal("0.75"),
                    energy_zero_events_total=4,
                    streak_lost_events_total=1,
                    referral_reward_milestone_events_total=0,
                    referral_reward_granted_events_total=1,
                    calculated_at=now_utc,
                ),
            ]
        )

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/internal/analytics/executive?days=2",
            headers={"X-Internal-Token": get_settings().internal_api_token},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["days"] == 2
    assert len(payload["rows"]) == 2
    assert payload["rows"][0]["local_date_berlin"] == "2026-02-19"
    assert payload["rows"][1]["local_date_berlin"] == "2026-02-18"
    assert payload["rows"][0]["dau"] == 12
    assert payload["rows"][0]["purchase_rate"] == pytest.approx(0.333333, rel=1e-6)
    assert payload["rows"][0]["gameplay_completion_rate"] == pytest.approx(0.8)
