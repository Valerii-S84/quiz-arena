from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.promo_repo import PromoRepo
from app.economy.promo.constants import (
    FAILED_PROMO_ATTEMPT_RESULTS,
    PROMO_ATTEMPT_BLOCK_WINDOW,
    PROMO_ATTEMPT_MAX_FAILURES,
    PROMO_ATTEMPT_RATE_LIMIT_WINDOW,
)
from app.economy.promo.errors import PromoRateLimitedError


async def enforce_rate_limit(
    session: AsyncSession,
    *,
    user_id: int,
    now_utc: datetime,
) -> None:
    block_since = now_utc - PROMO_ATTEMPT_BLOCK_WINDOW
    recently_rate_limited = await PromoRepo.count_user_attempts(
        session,
        user_id=user_id,
        since_utc=block_since,
        attempt_results=("RATE_LIMITED",),
    )
    if recently_rate_limited > 0:
        raise PromoRateLimitedError

    window_start = now_utc - PROMO_ATTEMPT_RATE_LIMIT_WINDOW
    failed_attempts = await PromoRepo.count_user_attempts(
        session,
        user_id=user_id,
        since_utc=window_start,
        attempt_results=FAILED_PROMO_ATTEMPT_RESULTS,
    )
    if failed_attempts < PROMO_ATTEMPT_MAX_FAILURES:
        return

    last_failed_at = await PromoRepo.get_last_user_attempt_at(
        session,
        user_id=user_id,
        since_utc=window_start,
        attempt_results=FAILED_PROMO_ATTEMPT_RESULTS,
    )
    if last_failed_at is not None and last_failed_at > block_since:
        raise PromoRateLimitedError
