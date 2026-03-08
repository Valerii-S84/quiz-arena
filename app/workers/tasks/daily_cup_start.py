from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tournament_participants import TournamentParticipant
from app.db.models.tournaments import Tournament
from app.game.tournaments.constants import TOURNAMENT_STATUS_ROUND_1
from app.game.tournaments.daily_cup_slots import get_round_deadline
from app.game.tournaments.rounds import create_round_matches


async def start_daily_arena_round_one(
    session: AsyncSession,
    *,
    tournament: Tournament,
    participants: list[TournamentParticipant],
    now_utc: datetime,
) -> None:
    next_round_deadline = get_round_deadline(
        round_number=1,
        tournament_start=tournament.registration_deadline,
    )
    await create_round_matches(
        session,
        tournament=tournament,
        round_no=1,
        participants=participants,
        previous_pairs=set(),
        bye_history=set(),
        deadline=next_round_deadline,
        now_utc=now_utc,
    )
    tournament.current_round = 1
    tournament.status = TOURNAMENT_STATUS_ROUND_1
    tournament.round_deadline = next_round_deadline
