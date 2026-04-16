from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DailyCupProofCardsContext:
    parsed_tournament_id: UUID
    participants: list[Any]
    participants_total: int
    standings_user_ids: list[int]
    participant_rows: dict[int, Any]
    points_by_user: dict[int, str]
    user_labels: dict[int, str]
    telegram_targets: dict[int, int | None]
    rounds_played: int


async def load_daily_cup_proof_cards_context(
    *,
    session: Any,
    parsed_tournament_id: UUID,
    user_id: int | None,
    now_utc: datetime,
    tournaments_repo: Any,
    users_repo: Any,
    matches_repo: Any,
    calculate_standings_fn: Any,
    format_points_fn: Any,
    format_user_label_fn: Any,
    is_today_daily_cup_tournament_fn: Any,
    logger: Any,
    daily_cup_tournament_types: set[str] | frozenset[str],
    tournament_completed_status: str,
    timezone_name: str,
) -> DailyCupProofCardsContext | None:
    tournament = await tournaments_repo.get_by_id(session, parsed_tournament_id)
    if (
        tournament is None
        or tournament.type not in daily_cup_tournament_types
        or tournament.status != tournament_completed_status
    ):
        return None
    if not is_today_daily_cup_tournament_fn(
        registration_deadline=tournament.registration_deadline,
        now_utc=now_utc,
        timezone_name=timezone_name,
    ):
        logger.info(
            "daily_cup_proof_cards_skipped_stale_tournament",
            tournament_id=str(parsed_tournament_id),
            registration_deadline=tournament.registration_deadline.isoformat(),
        )
        return None

    standings = await calculate_standings_fn(session, tournament_id=parsed_tournament_id)
    if not standings:
        return None

    all_participants = [item.participant for item in standings]
    participants = (
        [item for item in all_participants if int(item.user_id) == user_id]
        if user_id is not None
        else all_participants
    )
    users = await users_repo.list_by_ids(session, [int(item.user_id) for item in all_participants])
    rounds_played = await matches_repo.get_max_round_no(session, tournament_id=parsed_tournament_id)
    return DailyCupProofCardsContext(
        parsed_tournament_id=parsed_tournament_id,
        participants=participants,
        participants_total=len(all_participants),
        standings_user_ids=[item.user_id for item in standings],
        participant_rows={int(item.user_id): item for item in participants},
        points_by_user={
            int(item.user_id): format_points_fn(item.score) for item in all_participants
        },
        user_labels={
            int(user.id): format_user_label_fn(username=user.username, first_name=user.first_name)
            for user in users
        },
        telegram_targets={
            int(user.id): None if user.telegram_user_id is None else int(user.telegram_user_id)
            for user in users
        },
        rounds_played=rounds_played,
    )


__all__ = [
    "DailyCupProofCardsContext",
    "load_daily_cup_proof_cards_context",
]
