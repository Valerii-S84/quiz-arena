from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournament_participants import TournamentParticipant
from app.db.models.tournaments import Tournament
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.game.tournaments.constants import (
    TOURNAMENT_MATCH_STATUS_PENDING,
    TOURNAMENT_STATUS_REGISTRATION,
    TOURNAMENT_TYPE_DAILY_ARENA,
    TOURNAMENT_TYPE_PRIVATE,
)
from app.game.tournaments.errors import TournamentAccessError, TournamentNotFoundError
from app.game.tournaments.internal import build_tournament_snapshot
from app.game.tournaments.types import TournamentLobbySnapshot, TournamentParticipantSnapshot

_ROUND_STATUSES = frozenset({"ROUND_1", "ROUND_2", "ROUND_3"})


def _participant_snapshot(row: TournamentParticipant) -> TournamentParticipantSnapshot:
    return TournamentParticipantSnapshot(
        tournament_id=row.tournament_id,
        user_id=int(row.user_id),
        score=row.score,
        tie_break=row.tie_break,
        joined_at=row.joined_at,
    )


def _resolve_viewer_current_match(
    *,
    matches: list[TournamentMatch],
    viewer_user_id: int,
) -> tuple[UUID | None, int | None]:
    for match in matches:
        if int(match.user_a) == viewer_user_id:
            if match.user_b is None:
                return None, None
            if match.status != TOURNAMENT_MATCH_STATUS_PENDING:
                return None, int(match.user_b)
            return match.friend_challenge_id, int(match.user_b)
        if match.user_b is not None and int(match.user_b) == viewer_user_id:
            if match.status != TOURNAMENT_MATCH_STATUS_PENDING:
                return None, int(match.user_a)
            return match.friend_challenge_id, int(match.user_a)
    return None, None


async def _build_lobby_snapshot(
    *,
    session: AsyncSession,
    tournament: Tournament,
    viewer_user_id: int,
) -> TournamentLobbySnapshot:
    participants = await TournamentParticipantsRepo.list_for_tournament(
        session,
        tournament_id=tournament.id,
    )
    participant_snapshots = tuple(_participant_snapshot(item) for item in participants)
    participant_ids = {item.user_id for item in participant_snapshots}
    viewer_joined = viewer_user_id in participant_ids
    viewer_is_creator = tournament.created_by == viewer_user_id
    can_start = (
        viewer_is_creator
        and tournament.status == TOURNAMENT_STATUS_REGISTRATION
        and len(participant_snapshots) >= 2
    )

    viewer_match_challenge_id: UUID | None = None
    viewer_opponent_user_id: int | None = None
    if (
        viewer_joined
        and tournament.status in _ROUND_STATUSES
        and int(tournament.current_round) >= 1
    ):
        round_matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament.id,
            round_no=int(tournament.current_round),
        )
        viewer_match_challenge_id, viewer_opponent_user_id = _resolve_viewer_current_match(
            matches=round_matches,
            viewer_user_id=viewer_user_id,
        )

    return TournamentLobbySnapshot(
        tournament=build_tournament_snapshot(tournament),
        participants=participant_snapshots,
        viewer_joined=viewer_joined,
        viewer_is_creator=viewer_is_creator,
        can_start=can_start,
        viewer_current_match_challenge_id=viewer_match_challenge_id,
        viewer_current_opponent_user_id=viewer_opponent_user_id,
    )


async def get_private_tournament_lobby_by_id(
    session: AsyncSession,
    *,
    tournament_id: UUID,
    viewer_user_id: int,
) -> TournamentLobbySnapshot:
    tournament = await TournamentsRepo.get_by_id(session, tournament_id)
    if tournament is None:
        raise TournamentNotFoundError
    if tournament.type != TOURNAMENT_TYPE_PRIVATE:
        raise TournamentAccessError
    return await _build_lobby_snapshot(
        session=session,
        tournament=tournament,
        viewer_user_id=viewer_user_id,
    )


async def get_private_tournament_lobby_by_invite_code(
    session: AsyncSession,
    *,
    invite_code: str,
    viewer_user_id: int,
) -> TournamentLobbySnapshot:
    tournament = await TournamentsRepo.get_by_invite_code(session, invite_code)
    if tournament is None:
        raise TournamentNotFoundError
    if tournament.type != TOURNAMENT_TYPE_PRIVATE:
        raise TournamentAccessError
    return await _build_lobby_snapshot(
        session=session,
        tournament=tournament,
        viewer_user_id=viewer_user_id,
    )


async def get_daily_cup_lobby_by_id(
    session: AsyncSession,
    *,
    tournament_id: UUID,
    viewer_user_id: int,
) -> TournamentLobbySnapshot:
    tournament = await TournamentsRepo.get_by_id(session, tournament_id)
    if tournament is None:
        raise TournamentNotFoundError
    if tournament.type != TOURNAMENT_TYPE_DAILY_ARENA:
        raise TournamentAccessError
    return await _build_lobby_snapshot(
        session=session,
        tournament=tournament,
        viewer_user_id=viewer_user_id,
    )
