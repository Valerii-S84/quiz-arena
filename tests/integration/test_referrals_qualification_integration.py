from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models.referrals import Referral
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.referrals.constants import REFERRAL_STARTS_DAILY_LIMIT
from app.economy.referrals.service import ReferralService
from tests.integration.referrals_fixtures import UTC, _create_referral_row, _create_user, _seed_attempts


@pytest.mark.asyncio
async def test_referral_qualification_requires_20_attempts_on_two_local_days() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-qual")
    referred = await _create_user("referred-qual")

    await _create_referral_row(
        referrer_user_id=referrer.id,
        referred_user_id=referred.id,
        referral_code=referrer.referral_code,
        status="STARTED",
        created_at=now_utc - timedelta(days=3),
    )
    await _seed_attempts(
        user_id=referred.id,
        attempts_per_day=10,
        day_offsets=(1, 2),
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        result = await ReferralService.run_qualification_checks(session, now_utc=now_utc)
        assert result["qualified"] == 1

        stmt = select(Referral).where(Referral.referred_user_id == referred.id)
        referral = await session.scalar(stmt)
        assert referral is not None
        assert referral.status == "QUALIFIED"
        assert referral.qualified_at is not None


@pytest.mark.asyncio
async def test_started_referral_with_deleted_user_is_canceled() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-cancel")
    referred = await _create_user("referred-cancel")

    async with SessionLocal.begin() as session:
        user = await UsersRepo.get_by_id(session, referred.id)
        assert user is not None
        user.status = "DELETED"

    await _create_referral_row(
        referrer_user_id=referrer.id,
        referred_user_id=referred.id,
        referral_code=referrer.referral_code,
        status="STARTED",
        created_at=now_utc - timedelta(days=1),
    )

    async with SessionLocal.begin() as session:
        result = await ReferralService.run_qualification_checks(session, now_utc=now_utc)
        assert result["canceled"] == 1

        stmt = select(Referral).where(Referral.referred_user_id == referred.id)
        referral = await session.scalar(stmt)
        assert referral is not None
        assert referral.status == "CANCELED"


@pytest.mark.asyncio
async def test_velocity_limit_marks_extra_referral_as_rejected_fraud() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-velocity")

    for idx in range(REFERRAL_STARTS_DAILY_LIMIT + 1):
        referred = await _create_user(f"referred-velocity-{idx}")
        async with SessionLocal.begin() as session:
            referred_model = await UsersRepo.get_by_id(session, referred.id)
            assert referred_model is not None
            await ReferralService.register_start_for_new_user(
                session,
                referred_user=referred_model,
                referral_code=referrer.referral_code,
                now_utc=now_utc,
            )

    async with SessionLocal.begin() as session:
        stmt = (
            select(Referral)
            .where(Referral.referrer_user_id == referrer.id)
            .order_by(Referral.id.desc())
            .limit(1)
        )
        last_referral = await session.scalar(stmt)
        assert last_referral is not None
        assert last_referral.status == "REJECTED_FRAUD"
