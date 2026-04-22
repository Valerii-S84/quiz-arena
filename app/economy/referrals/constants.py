from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

QUALIFICATION_WINDOW = timedelta(days=14)
QUALIFICATION_MIN_ATTEMPTS = 20
QUALIFICATION_MIN_LOCAL_DAYS = 2

REWARD_DELAY = timedelta(hours=48)
QUALIFIED_REFERRALS_PER_REWARD = 3
REFERRAL_REWARDS_PER_MONTH_CAP = 2

REFERRAL_CYCLE_WINDOW = timedelta(days=30)
REFERRAL_STARTS_DAILY_LIMIT = 10

REWARD_CODE_PREMIUM_WEEK = "PREMIUM_WEEK"
REWARD_CODE_PREMIUM_STARTER = "PREMIUM_STARTER"
DEFAULT_REFERRAL_REWARD_CODE = REWARD_CODE_PREMIUM_STARTER


def normalize_referral_reward_code(reward_code: str) -> str:
    normalized = reward_code.strip().upper()
    if normalized == REWARD_CODE_PREMIUM_WEEK:
        return REWARD_CODE_PREMIUM_STARTER
    return normalized


FRAUD_SCORE_CYCLIC = Decimal("95.00")
FRAUD_SCORE_VELOCITY = Decimal("80.00")
