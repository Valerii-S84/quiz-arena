from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.db.repo.referrals_repo import ReferralsRepo
from app.db.repo.users_repo import UsersRepo


async def reserve_post_game_prompt(
    session: AsyncSession,
    *,
    user_id: int,
    now_utc: datetime,
) -> bool:
    user = await UsersRepo.get_by_id_for_update(session, user_id)
    if user is None:
        return False
    if user.referral_prompt_shown_at is not None:
        return False

    completed_sessions = await QuizSessionsRepo.count_completed_for_user(session, user_id=user_id)
    if completed_sessions not in {1, 2}:
        return False

    referrals_started = await ReferralsRepo.count_for_referrer(session, referrer_user_id=user_id)
    if referrals_started > 0:
        return False

    user.referral_prompt_shown_at = now_utc
    return True
