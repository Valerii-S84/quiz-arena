from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.db.models.friend_challenges import FriendChallenge


def user_did_not_finish_challenge(*, challenge: FriendChallenge, user_id: int) -> bool:
    total_rounds = max(1, int(challenge.total_rounds))
    if int(challenge.creator_user_id) == user_id:
        return (
            challenge.creator_finished_at is None
            and int(challenge.creator_answered_round) < total_rounds
        )
    if challenge.opponent_user_id is not None and int(challenge.opponent_user_id) == user_id:
        return (
            challenge.opponent_finished_at is None
            and int(challenge.opponent_answered_round) < total_rounds
        )
    return False


def collect_nonfinishers(
    *,
    matches: list[Any],
    challenges_by_id: dict[UUID, FriendChallenge],
) -> set[int]:
    nonfinishers: set[int] = set()
    for match in matches:
        if match.friend_challenge_id is None:
            continue
        challenge = challenges_by_id.get(match.friend_challenge_id)
        if challenge is None:
            continue
        user_a = int(match.user_a)
        if user_did_not_finish_challenge(challenge=challenge, user_id=user_a):
            nonfinishers.add(user_a)
        if match.user_b is not None:
            user_b = int(match.user_b)
            if user_did_not_finish_challenge(challenge=challenge, user_id=user_b):
                nonfinishers.add(user_b)
    return nonfinishers


@dataclass(frozen=True, slots=True)
class DailyCupNonfinishersSummaryContext:
    participants_total: int
    nonfinishers: list[int]
    telegram_targets: dict[int, int]


async def load_daily_cup_nonfinishers_summary_context(
    *,
    session: Any,
    parsed_tournament_id: UUID,
    tournaments_repo: Any,
    participants_repo: Any,
    users_repo: Any,
    matches_repo: Any,
    daily_cup_tournament_types: set[str] | frozenset[str],
    tournament_completed_status: str,
    collect_nonfinishers_fn: Any,
) -> DailyCupNonfinishersSummaryContext | None:
    tournament = await tournaments_repo.get_by_id(session, parsed_tournament_id)
    if (
        tournament is None
        or tournament.type not in daily_cup_tournament_types
        or tournament.status != tournament_completed_status
    ):
        return None

    participants = await participants_repo.list_for_tournament(
        session,
        tournament_id=parsed_tournament_id,
    )
    participant_user_ids = {int(item.user_id) for item in participants}
    if not participant_user_ids:
        return None

    users = await users_repo.list_by_ids(session, sorted(participant_user_ids))
    rounds_played = await matches_repo.get_max_round_no(
        session,
        tournament_id=parsed_tournament_id,
    )
    matches: list[Any] = []
    for round_no in range(1, rounds_played + 1):
        matches.extend(
            await matches_repo.list_by_tournament_round(
                session,
                tournament_id=parsed_tournament_id,
                round_no=round_no,
            )
        )

    challenge_ids = {
        match.friend_challenge_id for match in matches if match.friend_challenge_id is not None
    }
    challenges: list[FriendChallenge] = []
    if challenge_ids:
        result = await session.execute(
            select(FriendChallenge).where(FriendChallenge.id.in_(tuple(challenge_ids)))
        )
        challenges = list(result.scalars().all())

    return DailyCupNonfinishersSummaryContext(
        participants_total=len(participant_user_ids),
        nonfinishers=sorted(
            participant_user_ids
            & collect_nonfinishers_fn(
                matches=matches,
                challenges_by_id={challenge.id: challenge for challenge in challenges},
            )
        ),
        telegram_targets={int(user.id): int(user.telegram_user_id) for user in users},
    )


__all__ = [
    "DailyCupNonfinishersSummaryContext",
    "collect_nonfinishers",
    "load_daily_cup_nonfinishers_summary_context",
    "user_did_not_finish_challenge",
]
