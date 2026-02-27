from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tournament_participants import TournamentParticipant
from app.db.models.tournaments import Tournament
from app.db.repo.tournaments_repo import TournamentsRepo
from app.game.tournaments.constants import TOURNAMENT_DEFAULT_REGISTRATION_HOURS
from app.game.tournaments.errors import TournamentError
from app.game.tournaments.types import SwissParticipant, TournamentSnapshot


def build_tournament_snapshot(tournament: Tournament) -> TournamentSnapshot:
    return TournamentSnapshot(
        tournament_id=tournament.id,
        type=tournament.type,
        created_by=tournament.created_by,
        name=tournament.name,
        status=tournament.status,
        format=tournament.format,
        max_participants=tournament.max_participants,
        current_round=tournament.current_round,
        registration_deadline=tournament.registration_deadline,
        round_deadline=tournament.round_deadline,
        invite_code=tournament.invite_code,
        created_at=tournament.created_at,
    )


def resolve_registration_deadline(
    *,
    now_utc: datetime,
    registration_deadline: datetime | None,
) -> datetime:
    if registration_deadline is not None:
        return registration_deadline
    return now_utc + timedelta(hours=TOURNAMENT_DEFAULT_REGISTRATION_HOURS)


def resolve_round_deadline(*, now_utc: datetime, round_duration_hours: int) -> datetime:
    return now_utc + timedelta(hours=max(1, int(round_duration_hours)))


def participants_to_swiss(rows: list[TournamentParticipant]) -> list[SwissParticipant]:
    participants: list[SwissParticipant] = []
    for row in rows:
        participants.append(
            SwissParticipant(
                user_id=int(row.user_id),
                score=Decimal(row.score),
                tie_break=Decimal(row.tie_break),
                joined_at=row.joined_at,
            )
        )
    return participants


async def generate_invite_code(session: AsyncSession) -> str:
    for _ in range(10):
        code = uuid4().hex[:12]
        existing = await TournamentsRepo.get_by_invite_code(session, code)
        if existing is None:
            return code
    raise TournamentError("unable to generate invite code")
