from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.referrals_repo import ReferralsRepo
from app.economy.referrals.constants import (
    DEFAULT_REFERRAL_REWARD_CODE,
    REFERRAL_REWARDS_PER_MONTH_CAP,
    REWARD_DELAY,
)

from .overview import _build_reward_anchors
from .rewards_grant import _grant_reward
from .time_utils import _berlin_month_bounds_utc


async def run_reward_distribution(
    session: AsyncSession,
    *,
    now_utc: datetime,
    batch_size: int = 200,
    reward_code: str | None = DEFAULT_REFERRAL_REWARD_CODE,
) -> dict[str, int]:
    qualified_before_utc = now_utc - REWARD_DELAY
    referrer_ids = await ReferralsRepo.list_referrer_ids_with_reward_candidates(
        session,
        qualified_before_utc=qualified_before_utc,
        limit=batch_size,
    )
    month_start_utc, next_month_start_utc = _berlin_month_bounds_utc(now_utc)
    referrals_by_referrer = await ReferralsRepo.list_for_referrers_for_update(
        session,
        referrer_user_ids=referrer_ids,
    )

    result = {
        "referrers_examined": len(referrer_ids),
        "rewards_granted": 0,
        "deferred_limit": 0,
        "awaiting_choice": 0,
        "newly_notified": 0,
    }

    for referrer_user_id in referrer_ids:
        referrals = referrals_by_referrer.get(referrer_user_id, [])
        if not referrals:
            continue

        anchors = _build_reward_anchors(referrals)
        if not anchors:
            continue

        rewarded_this_month = sum(
            1
            for referral in referrals
            if referral.status == "REWARDED"
            and referral.rewarded_at is not None
            and referral.rewarded_at >= month_start_utc
            and referral.rewarded_at < next_month_start_utc
        )

        for referral in anchors:
            if referral.qualified_at is None or referral.qualified_at > qualified_before_utc:
                continue
            if referral.status == "REWARDED":
                continue

            if rewarded_this_month >= REFERRAL_REWARDS_PER_MONTH_CAP:
                if referral.status != "DEFERRED_LIMIT":
                    referral.status = "DEFERRED_LIMIT"
                    result["deferred_limit"] += 1
                continue

            if referral.status == "DEFERRED_LIMIT":
                referral.status = "QUALIFIED"

            if reward_code is None:
                result["awaiting_choice"] += 1
                if referral.notified_at is None:
                    referral.notified_at = now_utc
                    result["newly_notified"] += 1
                rewarded_this_month += 1
                continue

            await _grant_reward(
                session,
                user_id=referrer_user_id,
                referral_id=referral.id,
                reward_code=reward_code,
                now_utc=now_utc,
            )
            referral.status = "REWARDED"
            referral.rewarded_at = now_utc
            rewarded_this_month += 1
            result["rewards_granted"] += 1

    return result
