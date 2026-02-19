from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.db.models.referrals import Referral
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.main import app

UTC = timezone.utc


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=90_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"T{uuid4().hex[:10]}",
            username=None,
            first_name="ReferralReview",
            referred_by_user_id=None,
        )
        return user.id


async def _post_json(path: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            path,
            json=payload,
            headers={"X-Internal-Token": get_settings().internal_api_token},
        )
    return response.status_code, response.json()


@pytest.mark.asyncio
async def test_internal_referrals_review_queue_returns_filtered_cases() -> None:
    now_utc = datetime.now(UTC)
    referrer_id = await _create_user("review-queue-referrer")
    referred_fraud_id = await _create_user("review-queue-referred-fraud")
    referred_started_id = await _create_user("review-queue-referred-started")

    async with SessionLocal.begin() as session:
        referrer = await UsersRepo.get_by_id(session, referrer_id)
        assert referrer is not None
        session.add(
            Referral(
                referrer_user_id=referrer_id,
                referred_user_id=referred_fraud_id,
                referral_code=referrer.referral_code,
                status="REJECTED_FRAUD",
                qualified_at=None,
                rewarded_at=None,
                fraud_score=Decimal("95.00"),
                created_at=now_utc - timedelta(hours=1),
            )
        )
        session.add(
            Referral(
                referrer_user_id=referrer_id,
                referred_user_id=referred_started_id,
                referral_code=referrer.referral_code,
                status="STARTED",
                qualified_at=None,
                rewarded_at=None,
                fraud_score=Decimal("0"),
                created_at=now_utc - timedelta(hours=2),
            )
        )
        await session.flush()

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/internal/referrals/review-queue?window_hours=24&status=REJECTED_FRAUD&limit=20",
            headers={"X-Internal-Token": get_settings().internal_api_token},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status_filter"] == "REJECTED_FRAUD"
    assert len(payload["cases"]) == 1
    assert payload["cases"][0]["referrer_user_id"] == referrer_id
    assert payload["cases"][0]["referred_user_id"] == referred_fraud_id
    assert payload["cases"][0]["status"] == "REJECTED_FRAUD"


@pytest.mark.asyncio
async def test_internal_referrals_review_decision_confirm_fraud_and_reopen() -> None:
    now_utc = datetime.now(UTC)
    referrer_id = await _create_user("review-action-referrer")
    referred_id = await _create_user("review-action-referred")

    async with SessionLocal.begin() as session:
        referrer = await UsersRepo.get_by_id(session, referrer_id)
        assert referrer is not None
        referral = Referral(
            referrer_user_id=referrer_id,
            referred_user_id=referred_id,
            referral_code=referrer.referral_code,
            status="STARTED",
            qualified_at=None,
            rewarded_at=None,
            fraud_score=Decimal("0"),
            created_at=now_utc - timedelta(minutes=30),
        )
        session.add(referral)
        await session.flush()
        referral_id = int(referral.id)

    first_status, first_payload = await _post_json(
        f"/internal/referrals/{referral_id}/review",
        {
            "decision": "CONFIRM_FRAUD",
            "reason": "manual triage confirm",
            "expected_current_status": "STARTED",
        },
    )
    second_status, second_payload = await _post_json(
        f"/internal/referrals/{referral_id}/review",
        {
            "decision": "CONFIRM_FRAUD",
            "reason": "duplicate confirm",
            "expected_current_status": "REJECTED_FRAUD",
        },
    )
    third_status, third_payload = await _post_json(
        f"/internal/referrals/{referral_id}/review",
        {
            "decision": "REOPEN",
            "reason": "false positive",
            "expected_current_status": "REJECTED_FRAUD",
        },
    )

    assert first_status == 200
    assert first_payload["referral"]["status"] == "REJECTED_FRAUD"
    assert first_payload["referral"]["fraud_score"] >= 80.0
    assert first_payload["idempotent_replay"] is False

    assert second_status == 200
    assert second_payload["referral"]["status"] == "REJECTED_FRAUD"
    assert second_payload["idempotent_replay"] is True

    assert third_status == 200
    assert third_payload["referral"]["status"] == "STARTED"
    assert third_payload["referral"]["fraud_score"] == 0.0
    assert third_payload["idempotent_replay"] is False
