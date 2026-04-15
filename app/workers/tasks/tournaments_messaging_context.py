from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.game.tournaments.constants import TOURNAMENT_TYPE_PRIVATE


@dataclass(frozen=True, slots=True)
class TournamentRoundMessagingContext:
    parsed_tournament_id: UUID
    tournament: Any
    standings_user_ids: list[int]
    points_by_user: dict[int, str]
    place_by_user: dict[int, int]
    participant_rows: dict[int, Any]
    telegram_targets: dict[int, int]
    labels: dict[int, str]
    round_matches: list[Any]


async def load_round_messaging_context(
    *,
    session: Any,
    parsed_tournament_id: UUID,
    tournaments_repo: Any,
    participants_repo: Any,
    users_repo: Any,
    matches_repo: Any,
    format_points_fn: Callable[..., str],
    round_statuses: Collection[str],
    format_user_label_fn: Callable[..., str],
) -> TournamentRoundMessagingContext | None:
    tournament = await tournaments_repo.get_by_id(session, parsed_tournament_id)
    if (
        tournament is None
        or tournament.type != TOURNAMENT_TYPE_PRIVATE
        or tournament.status in {"REGISTRATION", "CANCELED"}
    ):
        return None

    participants = await participants_repo.list_for_tournament(
        session,
        tournament_id=parsed_tournament_id,
    )
    if not participants:
        return None

    users = await users_repo.list_by_ids(session, [int(item.user_id) for item in participants])
    round_matches: list[Any] = []
    if tournament.status in round_statuses:
        round_matches = await matches_repo.list_by_tournament_round(
            session,
            tournament_id=parsed_tournament_id,
            round_no=int(tournament.current_round),
        )

    standings_user_ids = [int(item.user_id) for item in participants]
    return TournamentRoundMessagingContext(
        parsed_tournament_id=parsed_tournament_id,
        tournament=tournament,
        standings_user_ids=standings_user_ids,
        points_by_user={int(item.user_id): format_points_fn(item.score) for item in participants},
        place_by_user={user_id: place for place, user_id in enumerate(standings_user_ids, start=1)},
        participant_rows={int(item.user_id): item for item in participants},
        telegram_targets={int(user.id): int(user.telegram_user_id) for user in users},
        labels={
            int(user.id): format_user_label_fn(username=user.username, first_name=user.first_name)
            for user in users
        },
        round_matches=round_matches,
    )


__all__ = ["TournamentRoundMessagingContext", "load_round_messaging_context"]
