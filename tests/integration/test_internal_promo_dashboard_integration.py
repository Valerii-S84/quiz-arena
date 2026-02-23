from __future__ import annotations

from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app
from tests.integration.promo_dashboard_fixtures import UTC, _seed_dashboard_dataset


@pytest.mark.asyncio
async def test_internal_promo_dashboard_returns_conversion_failure_and_guard_metrics() -> None:
    now_utc = datetime.now(UTC)
    await _seed_dashboard_dataset(now_utc)

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/internal/promo/dashboard?window_hours=24",
            headers={"X-Internal-Token": get_settings().internal_api_token},
        )

    assert response.status_code == 200
    payload = response.json()

    assert payload["window_hours"] == 24
    assert payload["attempts_total"] == 107
    assert payload["attempts_accepted"] == 2
    assert payload["attempts_failed"] == 105
    assert payload["acceptance_rate"] == pytest.approx(2 / 107)
    assert payload["failure_rate"] == pytest.approx(105 / 107)
    assert payload["attempt_failures_by_result"] == {
        "INVALID": 102,
        "EXPIRED": 1,
        "NOT_APPLICABLE": 1,
        "RATE_LIMITED": 1,
    }

    assert payload["redemptions_total"] == 4
    assert payload["redemptions_applied"] == 2
    assert payload["redemptions_by_status"] == {
        "APPLIED": 2,
        "EXPIRED": 1,
        "RESERVED": 1,
    }
    assert payload["discount_redemptions_total"] == 3
    assert payload["discount_redemptions_applied"] == 1
    assert payload["discount_redemptions_reserved"] == 1
    assert payload["discount_redemptions_expired"] == 1
    assert payload["discount_conversion_rate"] == pytest.approx(1 / 3)

    assert payload["guard_window_minutes"] == 10
    assert payload["guard_trigger_hashes"] == 1
    assert payload["active_campaigns_total"] == 2
    assert payload["paused_campaigns_total"] == 2
    assert payload["paused_campaigns_recent"] == 1
    assert payload["generated_at"]
