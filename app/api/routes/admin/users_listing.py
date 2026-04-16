from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models.daily_runs import DailyRun
from app.db.models.mode_progress import ModeProgress
from app.db.models.streak_state import StreakState
from app.db.models.users import User


def _build_search_filters(search: str) -> list[ColumnElement[bool]]:
    normalized = search.strip()
    if not normalized:
        return []

    filters: list[ColumnElement[bool]] = [
        User.username.ilike(f"%{normalized}%"),
        User.first_name.ilike(f"%{normalized}%"),
    ]
    if normalized.isdigit():
        numeric = int(normalized)
        filters.append(User.id == numeric)
        filters.append(User.telegram_user_id == numeric)
    return [or_(*filters)]


async def list_users_page(
    session: AsyncSession,
    *,
    search: str,
    language: str | None,
    level: str | None,
    page: int,
    limit: int,
    sort_by: str = "created_at",
) -> tuple[list[dict[str, object]], int]:
    filters: list[ColumnElement[bool]] = _build_search_filters(search)
    if language:
        filters.append(User.language_code == language)

    if level:
        level_exists = (
            select(ModeProgress.user_id)
            .where(ModeProgress.user_id == User.id, ModeProgress.preferred_level == level)
            .exists()
        )
        filters.append(level_exists)

    where_clause = and_(*filters) if filters else None
    total_stmt = select(func.count(User.id))
    if where_clause is not None:
        total_stmt = total_stmt.where(where_clause)
    total = int((await session.execute(total_stmt)).scalar_one() or 0)

    daily_totals_subquery = (
        select(
            DailyRun.user_id.label("user_id"),
            func.coalesce(func.sum(DailyRun.score), 0).label("daily_challenge_score"),
            func.count(DailyRun.id).label("daily_challenge_completed_runs"),
        )
        .where(DailyRun.status == "COMPLETED")
        .group_by(DailyRun.user_id)
        .subquery()
    )
    daily_challenge_score = func.coalesce(daily_totals_subquery.c.daily_challenge_score, 0)
    daily_challenge_completed_runs = func.coalesce(
        daily_totals_subquery.c.daily_challenge_completed_runs,
        0,
    )

    stmt = select(
        User,
        daily_challenge_score.label("daily_challenge_score"),
        daily_challenge_completed_runs.label("daily_challenge_completed_runs"),
    ).outerjoin(daily_totals_subquery, daily_totals_subquery.c.user_id == User.id)
    if where_clause is not None:
        stmt = stmt.where(where_clause)
    if sort_by == "daily_challenge_rating":
        stmt = stmt.order_by(
            daily_challenge_score.desc(),
            daily_challenge_completed_runs.desc(),
            User.created_at.desc(),
            User.id.desc(),
        )
    else:
        stmt = stmt.order_by(User.created_at.desc(), User.id.desc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    user_rows = list((await session.execute(stmt)).all())
    users = [user for user, _, _ in user_rows]

    user_ids = [int(user.id) for user in users]
    streak_stmt = select(StreakState.user_id, StreakState.current_streak).where(
        StreakState.user_id.in_(user_ids)
    )
    streak_map = {
        int(uid): int(streak) for uid, streak in (await session.execute(streak_stmt)).all()
    }

    rows: list[dict[str, object]] = [
        {
            "id": int(user.id),
            "telegram_user_id": int(user.telegram_user_id),
            "username": user.username,
            "first_name": user.first_name,
            "language": user.language_code,
            "status": user.status,
            "created_at": user.created_at.isoformat(),
            "last_seen_at": user.last_seen_at.isoformat() if user.last_seen_at else None,
            "streak": streak_map.get(int(user.id), 0),
            "daily_challenge_score": int(daily_score_raw or 0),
            "daily_challenge_completed_runs": int(daily_runs_raw or 0),
        }
        for user, daily_score_raw, daily_runs_raw in user_rows
    ]
    return rows, total
