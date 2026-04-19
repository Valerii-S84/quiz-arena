from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.game.sessions.types import StartSessionResult
from app.game.tournaments.constants import TOURNAMENT_TYPE_DAILY_ARENA

_DAILY_ARENA_CUP_HEADER_LABEL = "Daily Arena Cup"


async def resolve_friend_challenge_round_header_override(
    session: AsyncSession,
    *,
    tournament_match_id: UUID | None,
) -> str | None:
    if tournament_match_id is None:
        return None
    tournament_match = await TournamentMatchesRepo.get_by_id_for_update(
        session,
        tournament_match_id,
    )
    if tournament_match is None:
        return None
    tournament = await TournamentsRepo.get_by_id(session, tournament_match.tournament_id)
    if tournament is None or tournament.type != TOURNAMENT_TYPE_DAILY_ARENA:
        return None
    return _DAILY_ARENA_CUP_HEADER_LABEL


async def apply_friend_challenge_round_header_override(
    session: AsyncSession,
    *,
    start_result: StartSessionResult,
    tournament_match_id: UUID | None,
) -> None:
    start_result.session.header_mode_label_override = (
        await resolve_friend_challenge_round_header_override(
            session,
            tournament_match_id=tournament_match_id,
        )
    )
