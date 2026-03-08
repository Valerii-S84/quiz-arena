from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tournament_participants import TournamentParticipant
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournament_round_scores_repo import TournamentRoundScoresRepo


@dataclass(frozen=True, slots=True)
class DailyCupStanding:
    user_id: int
    place: int
    wins: int
    correct_answers: int
    total_time_ms: int
    participant: TournamentParticipant


async def calculate_daily_cup_standings(
    session: AsyncSession,
    *,
    tournament_id: UUID,
) -> list[DailyCupStanding]:
    participants = await TournamentParticipantsRepo.list_for_tournament(
        session,
        tournament_id=tournament_id,
    )
    try:
        aggregates = await TournamentRoundScoresRepo.list_standings_aggregates(
            session,
            tournament_id=tournament_id,
        )
    except AttributeError:
        aggregates = []
    aggregate_by_user = {item.player_id: item for item in aggregates}

    def _sort_key(item: TournamentParticipant) -> tuple[object, ...]:
        aggregate = aggregate_by_user.get(int(item.user_id))
        wins = 0 if aggregate is None else aggregate.wins
        correct_answers = 0 if aggregate is None else aggregate.correct_answers
        total_time_ms = 0 if aggregate is None else aggregate.total_time_ms
        joined_at = getattr(item, "joined_at", datetime(1970, 1, 1, tzinfo=timezone.utc))
        return (-wins, -correct_answers, total_time_ms, joined_at, int(item.user_id))

    ordered = sorted(
        participants,
        key=_sort_key,
    )
    standings: list[DailyCupStanding] = []
    for place, participant in enumerate(ordered, start=1):
        aggregate = aggregate_by_user.get(int(participant.user_id))
        standings.append(
            DailyCupStanding(
                user_id=int(participant.user_id),
                place=place,
                wins=0 if aggregate is None else aggregate.wins,
                correct_answers=0 if aggregate is None else aggregate.correct_answers,
                total_time_ms=0 if aggregate is None else aggregate.total_time_ms,
                participant=participant,
            )
        )
    return standings
