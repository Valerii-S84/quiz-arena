from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.tournaments import Tournament
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.game.tournaments.constants import (
    TOURNAMENT_DEFAULT_ROUND_DURATION_HOURS,
    TOURNAMENT_MATCH_STATUS_PENDING,
    TOURNAMENT_MAX_ROUNDS,
    TOURNAMENT_MIN_PARTICIPANTS,
    TOURNAMENT_STATUS_CANCELED,
    TOURNAMENT_STATUS_COMPLETED,
    TOURNAMENT_STATUS_REGISTRATION,
    TOURNAMENT_STATUS_ROUND_1,
    TOURNAMENT_STATUS_ROUND_2,
    TOURNAMENT_STATUS_ROUND_3,
    TOURNAMENT_TYPE_DAILY_ARENA,
    status_for_round,
)
from app.game.tournaments.internal import resolve_round_deadline
from app.game.tournaments.rounds import (
    collect_bye_history,
    collect_previous_pairs,
    create_round_matches,
)
from app.game.tournaments.settlement import settle_pending_match_from_duel

_ACTIVE_ROUND_STATUSES = frozenset(
    {
        TOURNAMENT_STATUS_ROUND_1,
        TOURNAMENT_STATUS_ROUND_2,
        TOURNAMENT_STATUS_ROUND_3,
    }
)


def _resolve_deadline_for_tournament(
    *,
    tournament: Tournament,
    now_utc: datetime,
    round_duration_hours: int,
) -> datetime:
    if tournament.type == TOURNAMENT_TYPE_DAILY_ARENA:
        return now_utc + timedelta(minutes=max(1, int(settings.daily_cup_round_duration_minutes)))
    return resolve_round_deadline(
        now_utc=now_utc,
        round_duration_hours=round_duration_hours,
    )


async def close_expired_registration(
    session: AsyncSession,
    *,
    tournament: Tournament,
) -> bool:
    if tournament.status != TOURNAMENT_STATUS_REGISTRATION:
        return False
    participants_total = await TournamentParticipantsRepo.count_for_tournament(
        session,
        tournament_id=tournament.id,
    )
    if participants_total >= TOURNAMENT_MIN_PARTICIPANTS:
        return False
    tournament.status = TOURNAMENT_STATUS_CANCELED
    tournament.round_deadline = None
    return True


async def settle_round_and_advance(
    session: AsyncSession,
    *,
    tournament: Tournament,
    now_utc: datetime,
    round_duration_hours: int = TOURNAMENT_DEFAULT_ROUND_DURATION_HOURS,
) -> dict[str, int]:
    current_round = max(1, int(tournament.current_round))
    round_matches = await TournamentMatchesRepo.list_by_tournament_round_for_update(
        session,
        tournament_id=tournament.id,
        round_no=current_round,
    )

    matches_settled = 0
    for match in round_matches:
        if await settle_pending_match_from_duel(session, match=match, now_utc=now_utc):
            matches_settled += 1

    pending_left = any(match.status == TOURNAMENT_MATCH_STATUS_PENDING for match in round_matches)
    if pending_left:
        return {
            "matches_settled": matches_settled,
            "matches_created": 0,
            "round_started": 0,
            "tournament_completed": 0,
        }

    if current_round >= TOURNAMENT_MAX_ROUNDS:
        tournament.status = TOURNAMENT_STATUS_COMPLETED
        tournament.round_deadline = None
        return {
            "matches_settled": matches_settled,
            "matches_created": 0,
            "round_started": 0,
            "tournament_completed": 1,
        }

    participants = await TournamentParticipantsRepo.list_for_tournament_for_update(
        session,
        tournament_id=tournament.id,
    )
    all_matches = await TournamentMatchesRepo.list_by_tournament_for_update(
        session,
        tournament_id=tournament.id,
    )
    next_round = current_round + 1
    next_deadline = _resolve_deadline_for_tournament(
        tournament=tournament,
        now_utc=now_utc,
        round_duration_hours=round_duration_hours,
    )
    matches_created = await create_round_matches(
        session,
        tournament=tournament,
        round_no=next_round,
        participants=participants,
        previous_pairs=collect_previous_pairs(matches=all_matches),
        bye_history=collect_bye_history(matches=all_matches),
        deadline=next_deadline,
        now_utc=now_utc,
    )
    tournament.current_round = next_round
    tournament.status = status_for_round(round_no=next_round)
    tournament.round_deadline = next_deadline
    return {
        "matches_settled": matches_settled,
        "matches_created": matches_created,
        "round_started": 1,
        "tournament_completed": 0,
    }


async def check_and_advance_round(
    session: AsyncSession,
    *,
    tournament_id: UUID,
    now_utc: datetime,
    round_duration_hours: int = TOURNAMENT_DEFAULT_ROUND_DURATION_HOURS,
) -> dict[str, int]:
    tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
    if tournament is None or tournament.status not in _ACTIVE_ROUND_STATUSES:
        return {
            "matches_settled": 0,
            "matches_created": 0,
            "round_started": 0,
            "tournament_completed": 0,
        }
    pending_matches = await TournamentMatchesRepo.count_pending_for_tournament_round(
        session,
        tournament_id=tournament.id,
        round_no=max(1, int(tournament.current_round)),
    )
    if pending_matches != 0:
        return {
            "matches_settled": 0,
            "matches_created": 0,
            "round_started": 0,
            "tournament_completed": 0,
        }
    return await settle_round_and_advance(
        session,
        tournament=tournament,
        now_utc=now_utc,
        round_duration_hours=round_duration_hours,
    )
