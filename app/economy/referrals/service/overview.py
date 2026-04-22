from __future__ import annotations

from datetime import datetime

from app.db.models.referrals import Referral
from app.economy.referrals.constants import (
    QUALIFIED_REFERRALS_PER_REWARD,
    REFERRAL_REWARDS_PER_MONTH_CAP,
    REWARD_DELAY,
)

from .models import ReferralOverview


def _build_reward_anchors(referrals: list[Referral]) -> list[Referral]:
    qualified_sequence = [
        referral
        for referral in referrals
        if referral.status in {"QUALIFIED", "DEFERRED_LIMIT", "REWARDED"}
        and referral.qualified_at is not None
    ]
    target_rewards_total = len(qualified_sequence) // QUALIFIED_REFERRALS_PER_REWARD
    return [
        qualified_sequence[(slot_index + 1) * QUALIFIED_REFERRALS_PER_REWARD - 1]
        for slot_index in range(target_rewards_total)
    ]


def _build_overview_from_referrals(
    *,
    referral_code: str,
    referrals: list[Referral],
    now_utc: datetime,
    rewarded_this_month: int,
) -> ReferralOverview:
    anchors = _build_reward_anchors(referrals)
    qualified_total = sum(
        1
        for referral in referrals
        if referral.status in {"QUALIFIED", "DEFERRED_LIMIT", "REWARDED"}
    )
    rewarded_total = sum(1 for referral in referrals if referral.status == "REWARDED")
    pending_rewards_total = max(0, len(anchors) - rewarded_total)
    progress_qualified = min(
        QUALIFIED_REFERRALS_PER_REWARD,
        max(0, qualified_total - (rewarded_total * QUALIFIED_REFERRALS_PER_REWARD)),
    )

    claimable_rewards = 0
    deferred_rewards = 0
    next_reward_at_utc: datetime | None = None
    monthly_slots_used = rewarded_this_month
    eligible_before_utc = now_utc - REWARD_DELAY
    for anchor in anchors:
        if anchor.status == "REWARDED" or anchor.qualified_at is None:
            continue
        if anchor.qualified_at > eligible_before_utc:
            available_at_utc = anchor.qualified_at + REWARD_DELAY
            if next_reward_at_utc is None or available_at_utc < next_reward_at_utc:
                next_reward_at_utc = available_at_utc
            continue
        if monthly_slots_used >= REFERRAL_REWARDS_PER_MONTH_CAP:
            deferred_rewards += 1
            continue
        claimable_rewards += 1
        monthly_slots_used += 1

    return ReferralOverview(
        referral_code=referral_code,
        qualified_total=qualified_total,
        rewarded_total=rewarded_total,
        progress_qualified=progress_qualified,
        progress_target=QUALIFIED_REFERRALS_PER_REWARD,
        pending_rewards_total=pending_rewards_total,
        claimable_rewards=claimable_rewards,
        deferred_rewards=deferred_rewards,
        next_reward_at_utc=next_reward_at_utc,
    )
