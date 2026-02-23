from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.db.models.referrals import Referral
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.services.user_onboarding import UserOnboardingService
from tests.integration.referrals_fixtures import _create_user, _telegram_user


@pytest.mark.asyncio
async def test_start_payload_referral_creates_started_referral_for_new_user() -> None:
    referrer = await _create_user("referrer-start")
    payload = f"ref_{referrer.referral_code}"

    telegram_user = _telegram_user(60_000_000_001)
    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=telegram_user,
            start_payload=payload,
        )
        referred_user = await UsersRepo.get_by_id(session, snapshot.user_id)
        assert referred_user is not None
        assert referred_user.referred_by_user_id == referrer.id

        stmt = select(Referral).where(Referral.referred_user_id == referred_user.id)
        referral = await session.scalar(stmt)
        assert referral is not None
        assert referral.referrer_user_id == referrer.id
        assert referral.status == "STARTED"


@pytest.mark.asyncio
async def test_existing_user_start_payload_does_not_rebind_referrer() -> None:
    referrer_a = await _create_user("referrer-a")
    referrer_b = await _create_user("referrer-b")
    telegram_user = _telegram_user(60_000_000_101)

    async with SessionLocal.begin() as session:
        first = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=telegram_user,
            start_payload=f"ref_{referrer_a.referral_code}",
        )
        second = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=telegram_user,
            start_payload=f"ref_{referrer_b.referral_code}",
        )
        assert first.user_id == second.user_id

        user = await UsersRepo.get_by_id(session, first.user_id)
        assert user is not None
        assert user.referred_by_user_id == referrer_a.id

        stmt = select(func.count(Referral.id)).where(Referral.referred_user_id == first.user_id)
        assert int(await session.scalar(stmt) or 0) == 1
