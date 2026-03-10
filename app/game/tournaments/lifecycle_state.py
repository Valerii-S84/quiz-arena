from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.db.models.tournaments import Tournament
from app.game.tournaments.constants import (
    TOURNAMENT_STATUS_CANCELED,
    TOURNAMENT_STATUS_COMPLETED,
    TOURNAMENT_TYPE_DAILY_ARENA,
    status_for_round,
)
from app.game.tournaments.daily_cup_slots import get_round_deadline
from app.game.tournaments.internal import resolve_round_deadline


def build_transition_result(
    *,
    matches_settled: int = 0,
    matches_created: int = 0,
    round_started: int = 0,
    tournament_completed: int = 0,
) -> dict[str, int]:
    return {
        "matches_settled": matches_settled,
        "matches_created": matches_created,
        "round_started": round_started,
        "tournament_completed": tournament_completed,
    }


def mark_tournament_canceled(*, tournament: Tournament) -> None:
    tournament.status = TOURNAMENT_STATUS_CANCELED
    tournament.round_deadline = None
    tournament.round_start_time = None


def mark_tournament_completed(*, tournament: Tournament) -> None:
    tournament.status = TOURNAMENT_STATUS_COMPLETED
    tournament.round_deadline = None
    tournament.round_start_time = None


def mark_round_started(
    *,
    tournament: Tournament,
    round_no: int,
    deadline: datetime,
    now_utc: datetime,
) -> None:
    tournament.current_round = round_no
    tournament.status = status_for_round(round_no=round_no)
    tournament.round_deadline = deadline
    if tournament.type == TOURNAMENT_TYPE_DAILY_ARENA:
        tournament.round_start_time = now_utc.replace(microsecond=0)


def enqueue_daily_cup_round_messaging(*, tournament_id: UUID) -> None:
    from app.workers.tasks.daily_cup_messaging import enqueue_daily_cup_round_messaging

    enqueue_daily_cup_round_messaging(tournament_id=str(tournament_id))


def resolve_deadline_for_tournament(
    *,
    tournament: Tournament,
    next_round: int,
    now_utc: datetime,
    round_duration_hours: int,
) -> datetime:
    if tournament.type == TOURNAMENT_TYPE_DAILY_ARENA:
        return get_round_deadline(
            round_number=next_round,
            tournament_start=tournament.registration_deadline,
        )
    return resolve_round_deadline(
        now_utc=now_utc,
        round_duration_hours=round_duration_hours,
    )
