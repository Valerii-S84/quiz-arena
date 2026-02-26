from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.quiz_attempts_repo import QuizAttemptsRepo
from app.db.repo.referrals_repo import ReferralsRepo
from app.db.repo.users_repo import UsersRepo
from app.economy.referrals.constants import (
    FRAUD_SCORE_CYCLIC,
    QUALIFICATION_MIN_ATTEMPTS,
    QUALIFICATION_MIN_LOCAL_DAYS,
    QUALIFICATION_WINDOW,
    REFERRAL_CYCLE_WINDOW,
)


async def run_qualification_checks(
    session: AsyncSession,
    *,
    now_utc: datetime,
    batch_size: int = 200,
    on_rejected_fraud: Callable[[int, int], Awaitable[None]] | None = None,
) -> dict[str, int]:
    started_ids = await ReferralsRepo.list_started_ids(session, limit=batch_size)
    result = {
        "examined": len(started_ids),
        "qualified": 0,
        "canceled": 0,
        "rejected_fraud": 0,
    }

    for referral_id in started_ids:
        referral = await ReferralsRepo.get_by_id_for_update(session, referral_id=referral_id)
        if referral is None or referral.status != "STARTED":
            continue

        reverse_pair = await ReferralsRepo.get_reverse_pair_since(
            session,
            referrer_user_id=referral.referrer_user_id,
            referred_user_id=referral.referred_user_id,
            since_utc=now_utc - REFERRAL_CYCLE_WINDOW,
        )
        if reverse_pair is not None:
            referral.status = "REJECTED_FRAUD"
            referral.fraud_score = FRAUD_SCORE_CYCLIC
            result["rejected_fraud"] += 1
            if on_rejected_fraud is not None:
                await on_rejected_fraud(int(referral.id), int(referral.referrer_user_id))
            continue

        referrer_user = await UsersRepo.get_by_id(session, referral.referrer_user_id)
        if referrer_user is None or referrer_user.status == "DELETED":
            referral.status = "CANCELED"
            result["canceled"] += 1
            continue

        referred_user = await UsersRepo.get_by_id(session, referral.referred_user_id)
        if referred_user is None or referred_user.status == "DELETED":
            referral.status = "CANCELED"
            result["canceled"] += 1
            continue

        qualification_window_end = referral.created_at + QUALIFICATION_WINDOW
        evaluation_window_end = min(now_utc, qualification_window_end)
        attempts_count = await QuizAttemptsRepo.count_user_attempts_between(
            session,
            user_id=referral.referred_user_id,
            from_utc=referral.created_at,
            to_utc=evaluation_window_end,
        )
        active_days_count = await QuizAttemptsRepo.count_user_active_local_days_between(
            session,
            user_id=referral.referred_user_id,
            from_utc=referral.created_at,
            to_utc=evaluation_window_end,
        )

        if (
            attempts_count >= QUALIFICATION_MIN_ATTEMPTS
            and active_days_count >= QUALIFICATION_MIN_LOCAL_DAYS
        ):
            referral.status = "QUALIFIED"
            referral.qualified_at = now_utc
            result["qualified"] += 1
            continue

        if now_utc >= qualification_window_end:
            referral.status = "CANCELED"
            result["canceled"] += 1

    return result
