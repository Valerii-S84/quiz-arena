from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.referrals_repo import ReferralsRepo
from app.db.repo.users_repo import UsersRepo
from app.economy.referrals.constants import (
    REFERRAL_REWARDS_PER_MONTH_CAP,
    REWARD_CODE_MEGA_PACK,
    REWARD_CODE_PREMIUM_STARTER,
    REWARD_DELAY,
)

from .models import ReferralClaimResult
from .overview import _build_overview_from_referrals, _build_reward_anchors
from .rewards_grant import _grant_reward
from .time_utils import _berlin_month_bounds_utc


async def claim_next_reward_choice(
    session: AsyncSession,
    *,
    user_id: int,
    reward_code: str,
    now_utc: datetime,
) -> ReferralClaimResult | None:
    normalized_reward_code = reward_code.strip().upper()
    if normalized_reward_code not in {
        REWARD_CODE_MEGA_PACK,
        REWARD_CODE_PREMIUM_STARTER,
    }:
        raise ValueError(f"unsupported reward code: {reward_code}")

    user = await UsersRepo.get_by_id(session, user_id)
    if user is None:
        return None

    referrals = await ReferralsRepo.list_for_referrer_for_update(
        session,
        referrer_user_id=user_id,
    )
    month_start_utc, next_month_start_utc = _berlin_month_bounds_utc(now_utc)
    rewarded_this_month = await ReferralsRepo.count_rewards_for_referrer_between(
        session,
        referrer_user_id=user_id,
        from_utc=month_start_utc,
        to_utc=next_month_start_utc,
    )

    anchors = _build_reward_anchors(referrals)
    eligible_before_utc = now_utc - REWARD_DELAY

    status = "NO_REWARD"
    deferred_limit_hit = False
    next_reward_at_utc: datetime | None = None
    for anchor in anchors:
        if anchor.status == "REWARDED" or anchor.qualified_at is None:
            continue
        if anchor.qualified_at > eligible_before_utc:
            available_at_utc = anchor.qualified_at + REWARD_DELAY
            if next_reward_at_utc is None or available_at_utc < next_reward_at_utc:
                next_reward_at_utc = available_at_utc
            continue

        if rewarded_this_month >= REFERRAL_REWARDS_PER_MONTH_CAP:
            if anchor.status != "DEFERRED_LIMIT":
                anchor.status = "DEFERRED_LIMIT"
            deferred_limit_hit = True
            continue

        await _grant_reward(
            session,
            user_id=user_id,
            referral_id=anchor.id,
            reward_code=normalized_reward_code,
            now_utc=now_utc,
        )
        anchor.status = "REWARDED"
        anchor.rewarded_at = now_utc
        rewarded_this_month += 1
        status = "CLAIMED"
        break

    if status != "CLAIMED":
        if deferred_limit_hit:
            status = "MONTHLY_CAP"
        elif next_reward_at_utc is not None:
            status = "TOO_EARLY"

    overview = _build_overview_from_referrals(
        referral_code=user.referral_code,
        referrals=referrals,
        now_utc=now_utc,
        rewarded_this_month=rewarded_this_month,
    )
    return ReferralClaimResult(
        status=status,
        reward_code=normalized_reward_code if status == "CLAIMED" else None,
        overview=overview,
    )
