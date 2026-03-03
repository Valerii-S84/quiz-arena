from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.game.tournaments.constants import TOURNAMENT_STATUS_COMPLETED, TOURNAMENT_TYPE_DAILY_ARENA

settings = get_settings()
_BADGE_STREAK_DAYS = 5


def _has_required_streak(*, joined_at_values: list[datetime], timezone_name: str) -> bool:
    if not joined_at_values:
        return False
    tz = ZoneInfo(timezone_name)
    local_dates = sorted({value.astimezone(tz).date() for value in joined_at_values})
    if len(local_dates) < _BADGE_STREAK_DAYS:
        return False
    streak = 1
    for index in range(1, len(local_dates)):
        delta_days = (local_dates[index] - local_dates[index - 1]).days
        if delta_days == 1:
            streak += 1
            if streak >= _BADGE_STREAK_DAYS:
                return True
        else:
            streak = 1
    return False


async def has_daily_cup_5_day_badge(session: AsyncSession, *, user_id: int) -> bool:
    joined_at_values = await TournamentParticipantsRepo.list_joined_at_for_user_by_tournament_type(
        session,
        user_id=user_id,
        tournament_type=TOURNAMENT_TYPE_DAILY_ARENA,
        tournament_status=TOURNAMENT_STATUS_COMPLETED,
        limit=365,
    )
    timezone_name = settings.daily_cup_timezone.strip() or "Europe/Berlin"
    return _has_required_streak(joined_at_values=joined_at_values, timezone_name=timezone_name)


__all__ = ["has_daily_cup_5_day_badge"]
