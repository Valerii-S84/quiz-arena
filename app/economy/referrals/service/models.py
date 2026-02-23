from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ReferralOverview:
    referral_code: str
    qualified_total: int
    rewarded_total: int
    progress_qualified: int
    progress_target: int
    pending_rewards_total: int
    claimable_rewards: int
    deferred_rewards: int
    next_reward_at_utc: datetime | None


@dataclass(frozen=True, slots=True)
class ReferralClaimResult:
    status: str
    reward_code: str | None
    overview: ReferralOverview
