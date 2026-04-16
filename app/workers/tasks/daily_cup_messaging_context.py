from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DailyCupRoundMessagingContext:
    parsed_tournament_id: UUID
    tournament: Any
    round_matches: list[Any]
    standings_user_ids: list[int]
    participants_total: int
    labels: dict[int, str]
    telegram_targets: dict[int, int]
    points_by_user: dict[int, str]
    tie_breaks_by_user: dict[int, str]
    place_by_user: dict[int, int]
    participant_rows: dict[int, Any]
    is_completed: bool
    allow_completion_followups: bool
    registration_deadline: datetime | None


async def load_daily_cup_round_messaging_context(
    *,
    session: Any,
    parsed_tournament_id: UUID,
    now_utc_value: datetime,
    tournaments_repo: Any,
    matches_repo: Any,
    users_repo: Any,
    calculate_standings_fn: Any,
    format_points_fn: Any,
    format_user_label_fn: Any,
    is_today_daily_cup_tournament_fn: Any,
    daily_cup_tournament_types: set[str] | frozenset[str],
    round_statuses: set[str] | frozenset[str],
    timezone_name: str,
) -> DailyCupRoundMessagingContext | None:
    tournament = await tournaments_repo.get_by_id(session, parsed_tournament_id)
    if (
        tournament is None
        or tournament.type not in daily_cup_tournament_types
        or tournament.status in {"REGISTRATION", "CANCELED"}
    ):
        return None

    standings = await calculate_standings_fn(session, tournament_id=parsed_tournament_id)
    if not standings:
        return None

    participants = [item.participant for item in standings]
    users = await users_repo.list_by_ids(session, [int(item.user_id) for item in participants])
    round_matches: list[Any] = []
    if tournament.status in round_statuses:
        round_matches = await matches_repo.list_by_tournament_round(
            session,
            tournament_id=parsed_tournament_id,
            round_no=int(tournament.current_round),
        )

    is_completed = tournament.status == "COMPLETED"
    allow_completion_followups = is_completed and is_today_daily_cup_tournament_fn(
        registration_deadline=tournament.registration_deadline,
        now_utc=now_utc_value,
        timezone_name=timezone_name,
    )
    return DailyCupRoundMessagingContext(
        parsed_tournament_id=parsed_tournament_id,
        tournament=tournament,
        round_matches=round_matches,
        standings_user_ids=[item.user_id for item in standings],
        participants_total=len(standings),
        labels={
            int(user.id): format_user_label_fn(username=user.username, first_name=user.first_name)
            for user in users
        },
        telegram_targets={int(user.id): int(user.telegram_user_id) for user in users},
        points_by_user={int(item.user_id): format_points_fn(item.score) for item in participants},
        tie_breaks_by_user={
            int(item.user_id): format_points_fn(item.tie_break) for item in participants
        },
        place_by_user={item.user_id: item.place for item in standings},
        participant_rows={int(item.user_id): item for item in participants},
        is_completed=is_completed,
        allow_completion_followups=allow_completion_followups,
        registration_deadline=tournament.registration_deadline,
    )


__all__ = [
    "DailyCupRoundMessagingContext",
    "load_daily_cup_round_messaging_context",
]
