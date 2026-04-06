from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_sessions import QuizSession


async def count_users_reaching_streak_threshold(
    session: AsyncSession,
    *,
    from_utc: datetime,
    to_utc: datetime,
    threshold: int,
) -> int:
    resolved_threshold = max(1, int(threshold))
    daily_activity = (
        select(
            QuizSession.user_id.label("user_id"),
            QuizSession.local_date_berlin.label("local_date_berlin"),
            func.min(QuizSession.completed_at).label("first_completed_at"),
        )
        .where(
            QuizSession.status == "COMPLETED",
            QuizSession.completed_at.is_not(None),
        )
        .group_by(QuizSession.user_id, QuizSession.local_date_berlin)
        .subquery()
    )
    ordered_days = (
        select(
            daily_activity.c.user_id,
            daily_activity.c.local_date_berlin,
            daily_activity.c.first_completed_at,
            (
                daily_activity.c.local_date_berlin
                - cast(
                    func.row_number().over(
                        partition_by=daily_activity.c.user_id,
                        order_by=daily_activity.c.local_date_berlin,
                    ),
                    Integer,
                )
            ).label("streak_group"),
        )
    ).subquery()
    streak_hits = (
        select(
            ordered_days.c.user_id,
            ordered_days.c.first_completed_at,
            func.row_number()
            .over(
                partition_by=(ordered_days.c.user_id, ordered_days.c.streak_group),
                order_by=ordered_days.c.local_date_berlin,
            )
            .label("streak_rank"),
        )
    ).subquery()
    first_hits_by_user = (
        select(
            streak_hits.c.user_id,
            func.min(streak_hits.c.first_completed_at).label("first_hit_at"),
        )
        .where(streak_hits.c.streak_rank == resolved_threshold)
        .group_by(streak_hits.c.user_id)
        .subquery()
    )
    stmt = select(func.count(first_hits_by_user.c.user_id)).where(
        first_hits_by_user.c.first_hit_at >= from_utc,
        first_hits_by_user.c.first_hit_at < to_utc,
    )
    return int((await session.execute(stmt)).scalar_one() or 0)
