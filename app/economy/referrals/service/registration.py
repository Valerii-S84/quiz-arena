from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.referrals import Referral
from app.db.models.users import User
from app.db.repo.referrals_repo import ReferralsRepo
from app.db.repo.users_repo import UsersRepo
from app.economy.referrals.constants import (
    FRAUD_SCORE_CYCLIC,
    FRAUD_SCORE_VELOCITY,
    REFERRAL_CYCLE_WINDOW,
    REFERRAL_STARTS_DAILY_LIMIT,
)

from .constants import START_PAYLOAD_REFERRAL_RE
from .time_utils import _berlin_day_bounds_utc


def extract_referral_code_from_start_payload(start_payload: str | None) -> str | None:
    if not start_payload:
        return None
    matched = START_PAYLOAD_REFERRAL_RE.match(start_payload.strip())
    if matched is None:
        return None
    return matched.group(1).upper()


async def register_start_for_new_user(
    session: AsyncSession,
    *,
    referred_user: User,
    referral_code: str,
    now_utc: datetime,
) -> str | None:
    normalized_code = referral_code.strip().upper()
    if not normalized_code:
        return None

    existing = await ReferralsRepo.get_by_referred_user_id(
        session,
        referred_user_id=referred_user.id,
    )
    if existing is not None:
        return existing.status

    referrer = await UsersRepo.get_by_referral_code(session, normalized_code)
    if referrer is None:
        return None
    if referrer.id == referred_user.id:
        return None
    if referrer.telegram_user_id == referred_user.telegram_user_id:
        return None

    reverse_pair = await ReferralsRepo.get_reverse_pair_since(
        session,
        referrer_user_id=referrer.id,
        referred_user_id=referred_user.id,
        since_utc=now_utc - REFERRAL_CYCLE_WINDOW,
    )
    if reverse_pair is not None:
        await ReferralsRepo.create(
            session,
            referral=Referral(
                referrer_user_id=referrer.id,
                referred_user_id=referred_user.id,
                referral_code=normalized_code,
                status="REJECTED_FRAUD",
                qualified_at=None,
                rewarded_at=None,
                fraud_score=FRAUD_SCORE_CYCLIC,
                created_at=now_utc,
            ),
        )
        return "REJECTED_FRAUD"

    day_start_utc, day_end_utc = _berlin_day_bounds_utc(now_utc)
    starts_today = await ReferralsRepo.count_referrer_starts_between(
        session,
        referrer_user_id=referrer.id,
        from_utc=day_start_utc,
        to_utc=day_end_utc,
    )
    is_velocity_abuse = starts_today + 1 > REFERRAL_STARTS_DAILY_LIMIT
    status = "REJECTED_FRAUD" if is_velocity_abuse else "STARTED"
    fraud_score = FRAUD_SCORE_VELOCITY if is_velocity_abuse else Decimal("0")

    await ReferralsRepo.create(
        session,
        referral=Referral(
            referrer_user_id=referrer.id,
            referred_user_id=referred_user.id,
            referral_code=normalized_code,
            status=status,
            qualified_at=None,
            rewarded_at=None,
            fraud_score=fraud_score,
            created_at=now_utc,
        ),
    )
    referred_user.referred_by_user_id = referrer.id
    return status
