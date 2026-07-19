from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.daily_push_logs import DailyPushLog
from app.db.models.daily_runs import DailyRun
from app.db.models.streak_state import StreakState
from app.db.models.tournament_participants import TournamentParticipant
from app.db.models.users import User


async def list_daily_push_targets(
    session: AsyncSession,
    *,
    berlin_date: date,
    push_kind: str,
    after_user_id: int | None,
    limit: int,
) -> list[tuple[int, int, int]]:
    resolved_limit = max(1, min(1000, int(limit)))
    completed_daily_exists = (
        select(DailyRun.id)
        .where(
            DailyRun.user_id == User.id,
            DailyRun.berlin_date == berlin_date,
            DailyRun.status == "COMPLETED",
        )
        .exists()
    )
    push_logged_exists = (
        select(DailyPushLog.user_id)
        .where(
            DailyPushLog.user_id == User.id,
            DailyPushLog.berlin_date == berlin_date,
            DailyPushLog.push_kind == push_kind,
        )
        .exists()
    )
    stmt = (
        select(
            User.id,
            User.telegram_user_id,
            func.coalesce(StreakState.current_streak, 0),
        )
        .outerjoin(StreakState, StreakState.user_id == User.id)
        .where(User.status == "ACTIVE", ~completed_daily_exists, ~push_logged_exists)
        .order_by(User.id.asc())
        .limit(resolved_limit)
    )
    if after_user_id is not None:
        stmt = stmt.where(User.id > after_user_id)

    result = await session.execute(stmt)
    return [
        (int(user_id_raw), int(telegram_user_id_raw), int(streak_raw))
        for user_id_raw, telegram_user_id_raw, streak_raw in result.all()
    ]


async def list_daily_cup_push_targets(
    session: AsyncSession,
    *,
    tournament_id,
    active_since_utc: datetime,
    after_user_id: int | None,
    limit: int,
) -> list[tuple[int, int]]:
    resolved_limit = max(1, min(1000, int(limit)))
    registered_exists = (
        select(TournamentParticipant.user_id)
        .where(
            TournamentParticipant.tournament_id == tournament_id,
            TournamentParticipant.user_id == User.id,
        )
        .exists()
    )
    stmt = (
        select(User.id, User.telegram_user_id)
        .where(
            User.status == "ACTIVE",
            User.last_seen_at.is_not(None),
            User.last_seen_at >= active_since_utc,
            ~registered_exists,
        )
        .order_by(User.id.asc())
        .limit(resolved_limit)
    )
    if after_user_id is not None:
        stmt = stmt.where(User.id > after_user_id)

    result = await session.execute(stmt)
    return [
        (int(user_id_raw), int(telegram_user_id_raw))
        for user_id_raw, telegram_user_id_raw in result.all()
    ]


async def list_daily_cup_registered_reminder_targets(
    session: AsyncSession,
    *,
    tournament_id,
    after_user_id: int | None,
    limit: int,
) -> list[tuple[int, int]]:
    resolved_limit = max(1, min(1000, int(limit)))
    stmt = (
        select(User.id, User.telegram_user_id)
        .join(
            TournamentParticipant,
            and_(
                TournamentParticipant.user_id == User.id,
                TournamentParticipant.tournament_id == tournament_id,
            ),
        )
        .where(
            User.status == "ACTIVE",
            or_(
                User.last_seen_at.is_(None),
                User.last_seen_at <= TournamentParticipant.joined_at,
            ),
        )
        .order_by(User.id.asc())
        .limit(resolved_limit)
    )
    if after_user_id is not None:
        stmt = stmt.where(User.id > after_user_id)

    result = await session.execute(stmt)
    return [
        (int(user_id_raw), int(telegram_user_id_raw))
        for user_id_raw, telegram_user_id_raw in result.all()
    ]
