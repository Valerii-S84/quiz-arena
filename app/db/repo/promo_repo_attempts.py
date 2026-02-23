from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.promo_attempts import PromoAttempt


async def create_attempt(session: AsyncSession, *, attempt: PromoAttempt) -> PromoAttempt:
    session.add(attempt)
    await session.flush()
    return attempt


async def count_user_attempts(
    session: AsyncSession,
    *,
    user_id: int,
    since_utc: datetime,
    attempt_results: Iterable[str] | None = None,
) -> int:
    stmt = select(func.count(PromoAttempt.id)).where(
        PromoAttempt.user_id == user_id,
        PromoAttempt.attempted_at >= since_utc,
    )
    if attempt_results is not None:
        values = tuple(attempt_results)
        if not values:
            return 0
        stmt = stmt.where(PromoAttempt.result.in_(values))

    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def count_attempts_by_result(
    session: AsyncSession,
    *,
    since_utc: datetime,
) -> dict[str, int]:
    stmt = (
        select(PromoAttempt.result, func.count(PromoAttempt.id))
        .where(PromoAttempt.attempted_at >= since_utc)
        .group_by(PromoAttempt.result)
    )
    result = await session.execute(stmt)
    return {str(status): int(count) for status, count in result.all()}


async def get_last_user_attempt_at(
    session: AsyncSession,
    *,
    user_id: int,
    since_utc: datetime,
    attempt_results: Iterable[str] | None = None,
) -> datetime | None:
    stmt = select(func.max(PromoAttempt.attempted_at)).where(
        PromoAttempt.user_id == user_id,
        PromoAttempt.attempted_at >= since_utc,
    )
    if attempt_results is not None:
        values = tuple(attempt_results)
        if not values:
            return None
        stmt = stmt.where(PromoAttempt.result.in_(values))

    result = await session.execute(stmt)
    return result.scalar_one()


async def get_abusive_code_hashes(
    session: AsyncSession,
    *,
    since_utc: datetime,
    min_failed_attempts: int,
    min_distinct_users: int,
) -> list[str]:
    stmt = (
        select(PromoAttempt.normalized_code_hash)
        .where(
            PromoAttempt.attempted_at >= since_utc,
            PromoAttempt.result.in_(("INVALID", "EXPIRED", "NOT_APPLICABLE")),
        )
        .group_by(PromoAttempt.normalized_code_hash)
        .having(
            func.count(PromoAttempt.id) > min_failed_attempts,
            func.count(distinct(PromoAttempt.user_id)) >= min_distinct_users,
        )
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_abusive_code_hashes(
    session: AsyncSession,
    *,
    since_utc: datetime,
    min_failed_attempts: int,
    min_distinct_users: int,
) -> int:
    code_hashes = await get_abusive_code_hashes(
        session,
        since_utc=since_utc,
        min_failed_attempts=min_failed_attempts,
        min_distinct_users=min_distinct_users,
    )
    return len(code_hashes)
