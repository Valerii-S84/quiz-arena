from __future__ import annotations

from .constants import START_PAYLOAD_REFERRAL_RE
from .models import ReferralClaimResult, ReferralOverview
from .overview import _build_overview_from_referrals, _build_reward_anchors
from .prompt import reserve_post_game_prompt
from .qualification import run_qualification_checks
from .queries import get_referrer_overview
from .registration import extract_referral_code_from_start_payload, register_start_for_new_user
from .rewards_claim import claim_next_reward_choice
from .rewards_distribution import run_reward_distribution
from .rewards_grant import _grant_mega_pack_reward, _grant_premium_starter_reward, _grant_reward
from .time_utils import _berlin_datetime, _berlin_day_bounds_utc, _berlin_month_bounds_utc


class ReferralService:
    extract_referral_code_from_start_payload = staticmethod(
        extract_referral_code_from_start_payload
    )
    _berlin_datetime = staticmethod(_berlin_datetime)
    _berlin_day_bounds_utc = staticmethod(_berlin_day_bounds_utc)
    _berlin_month_bounds_utc = staticmethod(_berlin_month_bounds_utc)
    _build_reward_anchors = staticmethod(_build_reward_anchors)
    _build_overview_from_referrals = staticmethod(_build_overview_from_referrals)
    get_referrer_overview = staticmethod(get_referrer_overview)
    register_start_for_new_user = staticmethod(register_start_for_new_user)
    reserve_post_game_prompt = staticmethod(reserve_post_game_prompt)
    run_qualification_checks = staticmethod(run_qualification_checks)
    _grant_mega_pack_reward = staticmethod(_grant_mega_pack_reward)
    _grant_premium_starter_reward = staticmethod(_grant_premium_starter_reward)
    _grant_reward = staticmethod(_grant_reward)
    claim_next_reward_choice = staticmethod(claim_next_reward_choice)
    run_reward_distribution = staticmethod(run_reward_distribution)


__all__ = [
    "START_PAYLOAD_REFERRAL_RE",
    "ReferralClaimResult",
    "ReferralOverview",
    "ReferralService",
]
