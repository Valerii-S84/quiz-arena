from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.referrals.service import ReferralService
from tests.integration.referrals_fixtures import (
    UTC,
    _create_referral_row,
    _create_user,
    _seed_attempts,
)


@pytest.mark.asyncio
async def test_post_game_referral_prompt_is_reserved_once() -> None:
    now_utc = datetime(2026, 2, 26, 12, 0, tzinfo=UTC)
    user = await _create_user("referral-prompt-once")
    await _seed_attempts(
        user_id=user.id,
        attempts_per_day=1,
        day_offsets=(1,),
        now_utc=now_utc,
    )

    async with SessionLocal.begin() as session:
        first = await ReferralService.reserve_post_game_prompt(
            session,
            user_id=user.id,
            now_utc=now_utc,
        )
        second = await ReferralService.reserve_post_game_prompt(
            session,
            user_id=user.id,
            now_utc=now_utc + timedelta(minutes=1),
        )
        user_row = await UsersRepo.get_by_id(session, user.id)
        assert user_row is not None
        assert user_row.referral_prompt_shown_at is not None

    assert first is True
    assert second is False


@pytest.mark.asyncio
async def test_post_game_referral_prompt_is_blocked_when_referrals_started() -> None:
    now_utc = datetime(2026, 2, 26, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referral-prompt-blocked-referrer")
    referred = await _create_user("referral-prompt-blocked-referred")
    await _seed_attempts(
        user_id=referrer.id,
        attempts_per_day=1,
        day_offsets=(1,),
        now_utc=now_utc,
    )
    await _create_referral_row(
        referrer_user_id=referrer.id,
        referred_user_id=referred.id,
        referral_code=referrer.referral_code,
        status="STARTED",
        created_at=now_utc - timedelta(hours=1),
    )

    async with SessionLocal.begin() as session:
        reserved = await ReferralService.reserve_post_game_prompt(
            session,
            user_id=referrer.id,
            now_utc=now_utc,
        )

    assert reserved is False
