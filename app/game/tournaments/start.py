from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.game.tournaments.constants import (
    TOURNAMENT_DEFAULT_ROUND_DURATION_HOURS,
    TOURNAMENT_MIN_PARTICIPANTS,
    TOURNAMENT_STATUS_REGISTRATION,
    TOURNAMENT_STATUS_ROUND_1,
    TOURNAMENT_TYPE_PRIVATE,
)
from app.game.tournaments.errors import (
    TournamentAccessError,
    TournamentAlreadyStartedError,
    TournamentInsufficientParticipantsError,
    TournamentNotFoundError,
)
from app.game.tournaments.internal import build_tournament_snapshot, resolve_round_deadline
from app.game.tournaments.rounds import create_round_matches
from app.game.tournaments.types import TournamentStartResult


async def start_private_tournament(
    session: AsyncSession,
    *,
    creator_user_id: int,
    tournament_id: UUID,
    now_utc: datetime,
    round_duration_hours: int = TOURNAMENT_DEFAULT_ROUND_DURATION_HOURS,
) -> TournamentStartResult:
    tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
    if tournament is None:
        raise TournamentNotFoundError
    if tournament.type != TOURNAMENT_TYPE_PRIVATE:
        raise TournamentAccessError
    if tournament.created_by != creator_user_id:
        raise TournamentAccessError
    if tournament.status != TOURNAMENT_STATUS_REGISTRATION:
        raise TournamentAlreadyStartedError

    participants = await TournamentParticipantsRepo.list_for_tournament_for_update(
        session,
        tournament_id=tournament.id,
    )
    if len(participants) < TOURNAMENT_MIN_PARTICIPANTS:
        raise TournamentInsufficientParticipantsError

    round_deadline = resolve_round_deadline(
        now_utc=now_utc,
        round_duration_hours=round_duration_hours,
    )
    matches_total = await create_round_matches(
        session,
        tournament=tournament,
        round_no=1,
        participants=participants,
        previous_pairs=set(),
        bye_history=set(),
        deadline=round_deadline,
        now_utc=now_utc,
    )
    tournament.status = TOURNAMENT_STATUS_ROUND_1
    tournament.current_round = 1
    tournament.round_deadline = round_deadline
    return TournamentStartResult(
        snapshot=build_tournament_snapshot(tournament),
        round_no=1,
        matches_total=matches_total,
    )
