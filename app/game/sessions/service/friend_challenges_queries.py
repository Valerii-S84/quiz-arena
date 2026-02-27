from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.friend_challenges.constants import normalize_duel_status
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError
from app.game.sessions.types import FriendChallengeSnapshot

from .friend_challenges_internal import (
    _build_friend_challenge_snapshot,
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
)
from .friend_challenges_series_utils import _count_series_wins


async def get_friend_challenge_snapshot_for_user(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
) -> FriendChallengeSnapshot:
    challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
    if challenge is None:
        raise FriendChallengeNotFoundError
    challenge.status = normalize_duel_status(
        status=challenge.status,
        has_opponent=challenge.opponent_user_id is not None,
    )
    if _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
        await _emit_friend_challenge_expired_event(
            session,
            challenge=challenge,
            happened_at=now_utc,
            source=EVENT_SOURCE_BOT,
        )
    if user_id not in {challenge.creator_user_id, challenge.opponent_user_id}:
        raise FriendChallengeAccessError
    return _build_friend_challenge_snapshot(challenge)


async def get_friend_series_score_for_user(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
) -> tuple[int, int, int, int]:
    challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
    if challenge is None:
        raise FriendChallengeNotFoundError
    challenge.status = normalize_duel_status(
        status=challenge.status,
        has_opponent=challenge.opponent_user_id is not None,
    )
    if _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
        await _emit_friend_challenge_expired_event(
            session,
            challenge=challenge,
            happened_at=now_utc,
            source=EVENT_SOURCE_BOT,
        )
    if user_id not in {challenge.creator_user_id, challenge.opponent_user_id}:
        raise FriendChallengeAccessError
    if challenge.series_id is None or challenge.series_best_of <= 1:
        return (0, 0, 1, 1)

    series_challenges = await FriendChallengesRepo.list_by_series_id_for_update(
        session,
        series_id=challenge.series_id,
    )
    creator_wins, opponent_wins = _count_series_wins(
        series_challenges=series_challenges,
        creator_user_id=challenge.creator_user_id,
        opponent_user_id=challenge.opponent_user_id,
    )
    if user_id == challenge.creator_user_id:
        return (
            creator_wins,
            opponent_wins,
            challenge.series_game_number,
            challenge.series_best_of,
        )
    return (
        opponent_wins,
        creator_wins,
        challenge.series_game_number,
        challenge.series_best_of,
    )


async def list_friend_challenges_for_user(
    session: AsyncSession,
    *,
    user_id: int,
    now_utc: datetime,
    limit: int = 20,
) -> list[FriendChallengeSnapshot]:
    rows = await FriendChallengesRepo.list_recent_for_user(
        session,
        user_id=user_id,
        limit=limit,
    )
    snapshots: list[FriendChallengeSnapshot] = []
    for challenge in rows:
        challenge.status = normalize_duel_status(
            status=challenge.status,
            has_opponent=challenge.opponent_user_id is not None,
        )
        if _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
            await _emit_friend_challenge_expired_event(
                session,
                challenge=challenge,
                happened_at=now_utc,
                source=EVENT_SOURCE_BOT,
            )
        snapshots.append(_build_friend_challenge_snapshot(challenge))
    return snapshots
