from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tournaments import Tournament
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.game.tournaments.constants import (
    TOURNAMENT_DEFAULT_MAX_PARTICIPANTS,
    TOURNAMENT_FORMAT_QUICK_5,
    TOURNAMENT_FORMAT_QUICK_12,
    TOURNAMENT_MIN_PARTICIPANTS,
    TOURNAMENT_STATUS_REGISTRATION,
    TOURNAMENT_TYPE_DAILY_ARENA,
    TOURNAMENT_TYPE_PRIVATE,
)
from app.game.tournaments.errors import (
    TournamentAccessError,
    TournamentClosedError,
    TournamentFullError,
    TournamentNotFoundError,
)
from app.game.tournaments.internal import (
    build_tournament_snapshot,
    generate_invite_code,
    resolve_registration_deadline,
)
from app.game.tournaments.types import TournamentJoinResult, TournamentSnapshot


async def create_private_tournament(
    session: AsyncSession,
    *,
    created_by: int,
    format_code: str,
    now_utc: datetime,
    name: str | None = None,
    max_participants: int = TOURNAMENT_DEFAULT_MAX_PARTICIPANTS,
    registration_deadline: datetime | None = None,
) -> TournamentSnapshot:
    if format_code not in {TOURNAMENT_FORMAT_QUICK_5, TOURNAMENT_FORMAT_QUICK_12}:
        raise TournamentAccessError
    invite_code = await generate_invite_code(session)
    tournament = await TournamentsRepo.create(
        session,
        tournament=Tournament(
            id=uuid4(),
            type=TOURNAMENT_TYPE_PRIVATE,
            created_by=created_by,
            name=name,
            status=TOURNAMENT_STATUS_REGISTRATION,
            format=format_code,
            max_participants=max(
                TOURNAMENT_MIN_PARTICIPANTS,
                min(int(max_participants), TOURNAMENT_DEFAULT_MAX_PARTICIPANTS),
            ),
            current_round=0,
            registration_deadline=resolve_registration_deadline(
                now_utc=now_utc,
                registration_deadline=registration_deadline,
            ),
            round_deadline=None,
            invite_code=invite_code,
            created_at=now_utc,
        ),
    )
    await TournamentParticipantsRepo.create_once(
        session,
        tournament_id=tournament.id,
        user_id=created_by,
        joined_at=now_utc,
    )
    return build_tournament_snapshot(tournament)


async def join_private_tournament_by_code(
    session: AsyncSession,
    *,
    user_id: int,
    invite_code: str,
    now_utc: datetime,
) -> TournamentJoinResult:
    tournament = await TournamentsRepo.get_by_invite_code_for_update(session, invite_code)
    if tournament is None:
        raise TournamentNotFoundError
    if tournament.type != TOURNAMENT_TYPE_PRIVATE:
        raise TournamentAccessError
    if tournament.status != TOURNAMENT_STATUS_REGISTRATION:
        raise TournamentClosedError
    if tournament.registration_deadline <= now_utc:
        raise TournamentClosedError

    participants = await TournamentParticipantsRepo.list_for_tournament_for_update(
        session,
        tournament_id=tournament.id,
    )
    existing_user_ids = {int(item.user_id) for item in participants}
    if user_id in existing_user_ids:
        return TournamentJoinResult(
            snapshot=build_tournament_snapshot(tournament),
            joined_now=False,
            participants_total=len(existing_user_ids),
        )
    if len(existing_user_ids) >= int(tournament.max_participants):
        raise TournamentFullError

    joined_now = await TournamentParticipantsRepo.create_once(
        session,
        tournament_id=tournament.id,
        user_id=user_id,
        joined_at=now_utc,
    )
    participants_total = len(existing_user_ids) + int(joined_now)
    return TournamentJoinResult(
        snapshot=build_tournament_snapshot(tournament),
        joined_now=joined_now,
        participants_total=participants_total,
    )


async def join_daily_cup_by_id(
    session: AsyncSession,
    *,
    user_id: int,
    tournament_id: UUID,
    now_utc: datetime,
) -> TournamentJoinResult:
    tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
    if tournament is None:
        raise TournamentNotFoundError
    if tournament.type != TOURNAMENT_TYPE_DAILY_ARENA:
        raise TournamentAccessError
    if tournament.status != TOURNAMENT_STATUS_REGISTRATION:
        raise TournamentClosedError
    if tournament.registration_deadline <= now_utc:
        raise TournamentClosedError

    participants = await TournamentParticipantsRepo.list_for_tournament_for_update(
        session,
        tournament_id=tournament.id,
    )
    existing_user_ids = {int(item.user_id) for item in participants}
    if user_id in existing_user_ids:
        return TournamentJoinResult(
            snapshot=build_tournament_snapshot(tournament),
            joined_now=False,
            participants_total=len(existing_user_ids),
        )

    joined_now = await TournamentParticipantsRepo.create_once(
        session,
        tournament_id=tournament.id,
        user_id=user_id,
        joined_at=now_utc,
    )
    participants_total = len(existing_user_ids) + int(joined_now)
    return TournamentJoinResult(
        snapshot=build_tournament_snapshot(tournament),
        joined_now=joined_now,
        participants_total=participants_total,
    )
