from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.db.session import SessionLocal
from app.economy.referrals.service import ReferralService
from tests.integration.referrals_fixtures import (
    UTC,
    _create_paid_purchase,
    _create_referral_row,
    _create_user,
)


@pytest.mark.asyncio
async def test_referrer_overview_reports_progress_and_claimable_reward() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-overview")
    referred_users = [await _create_user(f"referred-overview-{idx}") for idx in range(3)]
    await _create_paid_purchase(user_id=referrer.id, now_utc=now_utc - timedelta(days=1))

    for referred in referred_users:
        await _create_referral_row(
            referrer_user_id=referrer.id,
            referred_user_id=referred.id,
            referral_code=referrer.referral_code,
            status="QUALIFIED",
            created_at=now_utc - timedelta(days=5),
            qualified_at=now_utc - timedelta(hours=49),
        )

    async with SessionLocal.begin() as session:
        overview = await ReferralService.get_referrer_overview(
            session,
            user_id=referrer.id,
            now_utc=now_utc,
        )
        assert overview is not None
        assert overview.qualified_total == 3
        assert overview.progress_qualified == 3
        assert overview.pending_rewards_total == 1
        assert overview.claimable_rewards == 1
        assert overview.next_reward_at_utc is None


@pytest.mark.asyncio
async def test_referrer_overview_hides_claimable_reward_without_paid_history() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-overview-no-paid-history")
    referred_users = [await _create_user(f"referred-overview-no-paid-{idx}") for idx in range(3)]

    for referred in referred_users:
        await _create_referral_row(
            referrer_user_id=referrer.id,
            referred_user_id=referred.id,
            referral_code=referrer.referral_code,
            status="QUALIFIED",
            created_at=now_utc - timedelta(days=5),
            qualified_at=now_utc - timedelta(hours=49),
        )

    async with SessionLocal.begin() as session:
        overview = await ReferralService.get_referrer_overview(
            session,
            user_id=referrer.id,
            now_utc=now_utc,
        )
        assert overview is not None
        assert overview.pending_rewards_total == 1
        assert overview.claimable_rewards == 0
        assert overview.next_reward_at_utc is None


@pytest.mark.asyncio
async def test_referrer_overview_keeps_zero_cost_purchase_locked() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-overview-zero-cost")
    referred_users = [await _create_user(f"referred-overview-zero-cost-{idx}") for idx in range(3)]
    await _create_paid_purchase(
        user_id=referrer.id,
        now_utc=now_utc - timedelta(days=1),
        stars_amount=0,
    )

    for referred in referred_users:
        await _create_referral_row(
            referrer_user_id=referrer.id,
            referred_user_id=referred.id,
            referral_code=referrer.referral_code,
            status="QUALIFIED",
            created_at=now_utc - timedelta(days=5),
            qualified_at=now_utc - timedelta(hours=49),
        )

    async with SessionLocal.begin() as session:
        overview = await ReferralService.get_referrer_overview(
            session,
            user_id=referrer.id,
            now_utc=now_utc,
        )
        assert overview is not None
        assert overview.pending_rewards_total == 1
        assert overview.claimable_rewards == 0
