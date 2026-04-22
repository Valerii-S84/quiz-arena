from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.db.models.entitlements import Entitlement
from app.db.models.referrals import Referral
from app.db.session import SessionLocal
from app.economy.referrals.constants import REWARD_CODE_PREMIUM_STARTER
from app.economy.referrals.service import ReferralService
from tests.integration.referrals_fixtures import UTC, _create_referral_row, _create_user


@pytest.mark.asyncio
async def test_claim_next_reward_choice_grants_selected_reward() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-claim-choice")
    referred_users = [await _create_user(f"referred-claim-choice-{idx}") for idx in range(3)]

    for referred in referred_users:
        await _create_referral_row(
            referrer_user_id=referrer.id,
            referred_user_id=referred.id,
            referral_code=referrer.referral_code,
            status="QUALIFIED",
            created_at=now_utc - timedelta(days=4),
            qualified_at=now_utc - timedelta(hours=49),
        )

    async with SessionLocal.begin() as session:
        claim = await ReferralService.claim_next_reward_choice(
            session,
            user_id=referrer.id,
            reward_code=REWARD_CODE_PREMIUM_STARTER,
            now_utc=now_utc,
        )
        assert claim is not None
        assert claim.status == "CLAIMED"
        assert claim.reward_code == REWARD_CODE_PREMIUM_STARTER
        assert claim.overview.rewarded_total == 1

        rewarded_stmt = select(func.count(Referral.id)).where(
            Referral.referrer_user_id == referrer.id,
            Referral.status == "REWARDED",
        )
        assert int(await session.scalar(rewarded_stmt) or 0) == 1

        entitlement_stmt = select(func.count(Entitlement.id)).where(
            Entitlement.user_id == referrer.id,
            Entitlement.entitlement_type == "PREMIUM",
            Entitlement.status == "ACTIVE",
        )
        assert int(await session.scalar(entitlement_stmt) or 0) == 1


@pytest.mark.asyncio
async def test_claim_next_reward_choice_is_idempotent_on_duplicate_tap() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-claim-idempotent")
    referred_users = [await _create_user(f"referred-claim-idempotent-{idx}") for idx in range(3)]

    for referred in referred_users:
        await _create_referral_row(
            referrer_user_id=referrer.id,
            referred_user_id=referred.id,
            referral_code=referrer.referral_code,
            status="QUALIFIED",
            created_at=now_utc - timedelta(days=4),
            qualified_at=now_utc - timedelta(hours=49),
        )

    async with SessionLocal.begin() as session:
        first = await ReferralService.claim_next_reward_choice(
            session,
            user_id=referrer.id,
            reward_code=REWARD_CODE_PREMIUM_STARTER,
            now_utc=now_utc,
        )
        second = await ReferralService.claim_next_reward_choice(
            session,
            user_id=referrer.id,
            reward_code=REWARD_CODE_PREMIUM_STARTER,
            now_utc=now_utc,
        )

    assert first is not None
    assert second is not None
    assert first.status == "CLAIMED"
    assert second.status == "NO_REWARD"

    async with SessionLocal.begin() as session:
        rewarded_stmt = select(func.count(Referral.id)).where(
            Referral.referrer_user_id == referrer.id,
            Referral.status == "REWARDED",
        )
        assert int(await session.scalar(rewarded_stmt) or 0) == 1

        entitlement_stmt = select(func.count(Entitlement.id)).where(
            Entitlement.user_id == referrer.id,
            Entitlement.entitlement_type == "PREMIUM",
            Entitlement.status == "ACTIVE",
        )
        assert int(await session.scalar(entitlement_stmt) or 0) == 1


@pytest.mark.asyncio
async def test_claim_next_reward_choice_is_safe_under_concurrent_duplicate_callbacks() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-claim-concurrent")
    referred_users = [await _create_user(f"referred-claim-concurrent-{idx}") for idx in range(3)]

    for referred in referred_users:
        await _create_referral_row(
            referrer_user_id=referrer.id,
            referred_user_id=referred.id,
            referral_code=referrer.referral_code,
            status="QUALIFIED",
            created_at=now_utc - timedelta(days=4),
            qualified_at=now_utc - timedelta(hours=49),
        )

    async def _claim_once() -> str:
        async with SessionLocal.begin() as session:
            claim = await ReferralService.claim_next_reward_choice(
                session,
                user_id=referrer.id,
                reward_code=REWARD_CODE_PREMIUM_STARTER,
                now_utc=now_utc,
            )
            assert claim is not None
            return claim.status

    statuses = await asyncio.gather(_claim_once(), _claim_once())
    assert statuses.count("CLAIMED") == 1
    assert statuses.count("NO_REWARD") == 1

    async with SessionLocal.begin() as session:
        rewarded_stmt = select(func.count(Referral.id)).where(
            Referral.referrer_user_id == referrer.id,
            Referral.status == "REWARDED",
        )
        assert int(await session.scalar(rewarded_stmt) or 0) == 1

        entitlement_stmt = select(func.count(Entitlement.id)).where(
            Entitlement.user_id == referrer.id,
            Entitlement.entitlement_type == "PREMIUM",
            Entitlement.status == "ACTIVE",
        )
        assert int(await session.scalar(entitlement_stmt) or 0) == 1


@pytest.mark.asyncio
async def test_worker_awaiting_choice_and_user_claim_race_is_stable() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-worker-choice-race")
    referred_users = [await _create_user(f"referred-worker-choice-race-{idx}") for idx in range(3)]

    for referred in referred_users:
        await _create_referral_row(
            referrer_user_id=referrer.id,
            referred_user_id=referred.id,
            referral_code=referrer.referral_code,
            status="QUALIFIED",
            created_at=now_utc - timedelta(days=4),
            qualified_at=now_utc - timedelta(hours=49),
        )

    async def _run_worker() -> dict[str, int]:
        async with SessionLocal.begin() as session:
            return await ReferralService.run_reward_distribution(
                session,
                now_utc=now_utc,
                reward_code=None,
            )

    async def _claim_once() -> str:
        async with SessionLocal.begin() as session:
            claim = await ReferralService.claim_next_reward_choice(
                session,
                user_id=referrer.id,
                reward_code=REWARD_CODE_PREMIUM_STARTER,
                now_utc=now_utc,
            )
            assert claim is not None
            return claim.status

    worker_result, claim_status = await asyncio.gather(_run_worker(), _claim_once())
    assert claim_status == "CLAIMED"
    assert worker_result["awaiting_choice"] in {0, 1}

    async with SessionLocal.begin() as session:
        rewarded_stmt = select(func.count(Referral.id)).where(
            Referral.referrer_user_id == referrer.id,
            Referral.status == "REWARDED",
        )
        assert int(await session.scalar(rewarded_stmt) or 0) == 1

        entitlement_stmt = select(func.count(Entitlement.id)).where(
            Entitlement.user_id == referrer.id,
            Entitlement.entitlement_type == "PREMIUM",
            Entitlement.status == "ACTIVE",
        )
        assert int(await session.scalar(entitlement_stmt) or 0) == 1
