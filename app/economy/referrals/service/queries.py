from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.referrals_repo import ReferralsRepo
from app.db.repo.users_repo import UsersRepo

from .models import ReferralOverview
from .overview import _build_overview_from_referrals
from .time_utils import _berlin_month_bounds_utc


async def get_referrer_overview(
    session: AsyncSession,
    *,
    user_id: int,
    now_utc: datetime,
) -> ReferralOverview | None:
    user = await UsersRepo.get_by_id(session, user_id)
    if user is None:
        return None

    referrals = await ReferralsRepo.list_for_referrer(
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
    return _build_overview_from_referrals(
        referral_code=user.referral_code,
        referrals=referrals,
        now_utc=now_utc,
        rewarded_this_month=rewarded_this_month,
    )
