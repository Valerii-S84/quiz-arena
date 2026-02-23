from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.db.models.referrals import Referral
from app.db.session import SessionLocal
from app.economy.referrals.service import ReferralService
from tests.integration.referrals_fixtures import UTC, _create_referral_row, _create_user


@pytest.mark.asyncio
async def test_referral_rewards_apply_after_48h_delay_and_require_three_qualified() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-reward")
    referred_users = [await _create_user(f"referred-reward-{idx}") for idx in range(3)]

    for idx, referred in enumerate(referred_users):
        await _create_referral_row(
            referrer_user_id=referrer.id,
            referred_user_id=referred.id,
            referral_code=referrer.referral_code,
            status="QUALIFIED",
            created_at=now_utc - timedelta(days=5),
            qualified_at=now_utc - timedelta(hours=47 if idx == 0 else 49),
        )

    async with SessionLocal.begin() as session:
        early = await ReferralService.run_reward_distribution(session, now_utc=now_utc)
        assert early["rewards_granted"] == 0

    async with SessionLocal.begin() as session:
        late = await ReferralService.run_reward_distribution(
            session,
            now_utc=now_utc + timedelta(hours=2),
        )
        assert late["rewards_granted"] == 1

        rewarded_stmt = select(func.count(Referral.id)).where(
            Referral.referrer_user_id == referrer.id,
            Referral.status == "REWARDED",
        )
        rewarded_count = int(await session.scalar(rewarded_stmt) or 0)
        assert rewarded_count == 1


@pytest.mark.asyncio
async def test_referral_monthly_limit_defers_third_reward_and_releases_next_month() -> None:
    now_utc = datetime(2026, 2, 20, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-month-cap")
    referred_users = [await _create_user(f"referred-month-cap-{idx}") for idx in range(9)]

    for referred in referred_users:
        await _create_referral_row(
            referrer_user_id=referrer.id,
            referred_user_id=referred.id,
            referral_code=referrer.referral_code,
            status="QUALIFIED",
            created_at=now_utc - timedelta(days=7),
            qualified_at=now_utc - timedelta(days=3),
        )

    async with SessionLocal.begin() as session:
        first_month = await ReferralService.run_reward_distribution(session, now_utc=now_utc)
        assert first_month["rewards_granted"] == 2
        assert first_month["deferred_limit"] >= 1

        deferred_stmt = select(func.count(Referral.id)).where(
            Referral.referrer_user_id == referrer.id,
            Referral.status == "DEFERRED_LIMIT",
        )
        assert int(await session.scalar(deferred_stmt) or 0) >= 1

    async with SessionLocal.begin() as session:
        next_month = await ReferralService.run_reward_distribution(
            session,
            now_utc=datetime(2026, 3, 2, 0, 10, tzinfo=UTC),
        )
        assert next_month["rewards_granted"] >= 1


@pytest.mark.asyncio
async def test_reward_distribution_without_reward_code_keeps_reward_for_choice() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-awaiting-choice")
    referred_users = [await _create_user(f"referred-awaiting-choice-{idx}") for idx in range(3)]

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
        result = await ReferralService.run_reward_distribution(
            session,
            now_utc=now_utc,
            reward_code=None,
        )
        assert result["rewards_granted"] == 0
        assert result["awaiting_choice"] == 1

        rewarded_stmt = select(func.count(Referral.id)).where(
            Referral.referrer_user_id == referrer.id,
            Referral.status == "REWARDED",
        )
        assert int(await session.scalar(rewarded_stmt) or 0) == 0
