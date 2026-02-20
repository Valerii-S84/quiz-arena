from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.db.models.outbox_events import OutboxEvent
from app.db.session import SessionLocal
from app.main import app

UTC = timezone.utc


@pytest.mark.asyncio
async def test_internal_referrals_events_feed_returns_referral_reward_events_only() -> None:
    now_utc = datetime.now(UTC)
    async with SessionLocal.begin() as session:
        session.add_all(
            [
                OutboxEvent(
                    event_type="referral_reward_milestone_available",
                    payload={"awaiting_choice": 2},
                    status="SENT",
                    created_at=now_utc - timedelta(hours=2),
                ),
                OutboxEvent(
                    event_type="referral_reward_granted",
                    payload={"rewards_granted": 1},
                    status="FAILED",
                    created_at=now_utc - timedelta(hours=1),
                ),
                OutboxEvent(
                    event_type="offers_conversion_drop_detected",
                    payload={"conversion_rate": 0.01},
                    status="SENT",
                    created_at=now_utc - timedelta(minutes=30),
                ),
            ]
        )

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/internal/referrals/events?window_hours=24&limit=20",
            headers={"X-Internal-Token": get_settings().internal_api_token},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_events"] == 2
    assert payload["by_type"] == {
        "referral_reward_milestone_available": 1,
        "referral_reward_granted": 1,
    }
    assert payload["by_status"] == {
        "SENT": 1,
        "FAILED": 1,
    }
    assert len(payload["events"]) == 2
    assert payload["events"][0]["event_type"] == "referral_reward_granted"
    assert payload["events"][1]["event_type"] == "referral_reward_milestone_available"


@pytest.mark.asyncio
async def test_internal_referrals_events_feed_supports_event_type_filter() -> None:
    now_utc = datetime.now(UTC)
    async with SessionLocal.begin() as session:
        session.add_all(
            [
                OutboxEvent(
                    event_type="referral_reward_milestone_available",
                    payload={"awaiting_choice": 1},
                    status="SENT",
                    created_at=now_utc - timedelta(hours=2),
                ),
                OutboxEvent(
                    event_type="referral_reward_granted",
                    payload={"rewards_granted": 3},
                    status="SENT",
                    created_at=now_utc - timedelta(hours=1),
                ),
            ]
        )

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/internal/referrals/events?window_hours=24&event_type=referral_reward_granted&limit=20",
            headers={"X-Internal-Token": get_settings().internal_api_token},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["event_type_filter"] == "referral_reward_granted"
    assert payload["total_events"] == 1
    assert payload["by_type"] == {"referral_reward_granted": 1}
    assert payload["by_status"] == {"SENT": 1}
    assert len(payload["events"]) == 1
    assert payload["events"][0]["event_type"] == "referral_reward_granted"


@pytest.mark.asyncio
async def test_internal_referrals_events_feed_rejects_invalid_event_type() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/internal/referrals/events?event_type=invalid_event",
            headers={"X-Internal-Token": get_settings().internal_api_token},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "E_REFERRAL_EVENT_TYPE_INVALID"}}
