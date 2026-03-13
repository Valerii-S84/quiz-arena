from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.tournaments import Tournament
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.game.tournaments.constants import (
    TOURNAMENT_MATCH_STATUS_PENDING,
    TOURNAMENT_STATUS_COMPLETED,
    TOURNAMENT_STATUS_REGISTRATION,
)
from app.workers.tasks.daily_cup_config import DAILY_CUP_TOURNAMENT_TYPE

settings = get_settings()
_ROUND_STATUSES = frozenset({"ROUND_1", "ROUND_2", "ROUND_3", "ROUND_4", "BRACKET_LIVE"})


class DailyCupUserStatus(str, Enum):
    NO_TOURNAMENT = "NO_TOURNAMENT"
    INVITE_OPEN = "INVITE_OPEN"
    REGISTERED_WAITING = "REGISTERED_WAITING"
    ROUND_ACTIVE = "ROUND_ACTIVE"
    ROUND_WAITING = "ROUND_WAITING"
    COMPLETED = "COMPLETED"
    NOT_PARTICIPANT = "NOT_PARTICIPANT"


@dataclass(frozen=True, slots=True)
class DailyCupUserStatusSnapshot:
    status: DailyCupUserStatus
    tournament: Tournament | None


def _parse_hhmm(value: str, *, default_hour: int, default_minute: int) -> tuple[int, int]:
    try:
        hour_raw, minute_raw = value.strip().split(":", maxsplit=1)
        hour = int(hour_raw)
        minute = int(minute_raw)
    except (AttributeError, ValueError):
        return default_hour, default_minute
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return default_hour, default_minute
    return hour, minute


def _local_daily_cup_anchor(*, now_utc: datetime, hour: int, minute: int) -> datetime:
    timezone_name = settings.daily_cup_timezone.strip() or "Europe/Berlin"
    tz = ZoneInfo(timezone_name)
    local_now = now_utc.astimezone(tz)
    return datetime(
        local_now.year,
        local_now.month,
        local_now.day,
        hour,
        minute,
        tzinfo=tz,
    )


def _invite_open_at_utc(*, now_utc: datetime) -> datetime:
    invite_time_value = os.getenv("DAILY_CUP_INVITE_TIME", "16:00")
    invite_hour, invite_minute = _parse_hhmm(invite_time_value, default_hour=16, default_minute=0)
    return _local_daily_cup_anchor(
        now_utc=now_utc, hour=invite_hour, minute=invite_minute
    ).astimezone(timezone.utc)


def _close_at_utc(*, now_utc: datetime) -> datetime:
    close_time_value = os.getenv("DAILY_CUP_CLOSE_TIME", settings.daily_cup_registration_close)
    close_hour, close_minute = _parse_hhmm(close_time_value, default_hour=18, default_minute=0)
    return _local_daily_cup_anchor(
        now_utc=now_utc, hour=close_hour, minute=close_minute
    ).astimezone(timezone.utc)


def _has_pending_round_match_for_user(*, user_id: int, matches: list) -> bool:
    for match in matches:
        is_user_match = int(match.user_a) == user_id or (
            match.user_b is not None and int(match.user_b) == user_id
        )
        if is_user_match and match.status == TOURNAMENT_MATCH_STATUS_PENDING:
            return True
    return False


def _daily_cup_type_priority() -> tuple[str]:
    return (DAILY_CUP_TOURNAMENT_TYPE,)


async def get_daily_cup_status_for_user(
    session: AsyncSession,
    *,
    user_id: int,
    now_utc: datetime,
) -> DailyCupUserStatusSnapshot:
    if now_utc < _invite_open_at_utc(now_utc=now_utc):
        return DailyCupUserStatusSnapshot(status=DailyCupUserStatus.NO_TOURNAMENT, tournament=None)

    tournament = None
    close_at_utc = _close_at_utc(now_utc=now_utc)
    for tournament_type in _daily_cup_type_priority():
        tournament = await TournamentsRepo.get_by_type_and_registration_deadline(
            session,
            tournament_type=tournament_type,
            registration_deadline=close_at_utc,
        )
        if tournament is not None:
            break
    if tournament is None:
        return DailyCupUserStatusSnapshot(status=DailyCupUserStatus.NO_TOURNAMENT, tournament=None)

    participants = await TournamentParticipantsRepo.list_for_tournament(
        session,
        tournament_id=tournament.id,
    )
    viewer_joined = user_id in {int(item.user_id) for item in participants}

    if tournament.status == TOURNAMENT_STATUS_REGISTRATION:
        if viewer_joined:
            return DailyCupUserStatusSnapshot(
                status=DailyCupUserStatus.REGISTERED_WAITING,
                tournament=tournament,
            )
        return DailyCupUserStatusSnapshot(
            status=DailyCupUserStatus.INVITE_OPEN, tournament=tournament
        )

    if tournament.status in _ROUND_STATUSES:
        if not viewer_joined:
            return DailyCupUserStatusSnapshot(
                status=DailyCupUserStatus.NOT_PARTICIPANT,
                tournament=tournament,
            )
        round_matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament.id,
            round_no=max(1, int(tournament.current_round)),
        )
        if _has_pending_round_match_for_user(user_id=user_id, matches=round_matches):
            return DailyCupUserStatusSnapshot(
                status=DailyCupUserStatus.ROUND_ACTIVE,
                tournament=tournament,
            )
        return DailyCupUserStatusSnapshot(
            status=DailyCupUserStatus.ROUND_WAITING, tournament=tournament
        )

    if tournament.status == TOURNAMENT_STATUS_COMPLETED:
        # TODO: completed Arena не розрізняє winner від інших учасників
        # Технічно можливо через daily_cup_standings.py (place == 1)
        # але потребує додавання WINNER статусу в DailyCupUserStatus enum
        # і окремого запиту standings — це окрема задача, не cleanup
        # Зараз: будь-який учасник completed турніру отримує COMPLETED
        return DailyCupUserStatusSnapshot(
            status=(
                DailyCupUserStatus.COMPLETED
                if viewer_joined
                else DailyCupUserStatus.NOT_PARTICIPANT
            ),
            tournament=tournament,
        )

    return DailyCupUserStatusSnapshot(status=DailyCupUserStatus.NO_TOURNAMENT, tournament=None)


__all__ = ["DailyCupUserStatus", "DailyCupUserStatusSnapshot", "get_daily_cup_status_for_user"]
