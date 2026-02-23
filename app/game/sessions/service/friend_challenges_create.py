from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError
from app.game.sessions.types import FriendChallengeSnapshot

from .constants import FRIEND_CHALLENGE_TOTAL_ROUNDS
from .friend_challenges_internal import (
    _build_friend_challenge_snapshot,
    _count_series_wins,
    _create_friend_challenge_row,
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
    _resolve_challenge_opponent_user_id,
    _resolve_friend_challenge_access_type,
    _series_wins_needed,
)


async def create_friend_challenge(
    session: AsyncSession,
    *,
    creator_user_id: int,
    mode_code: str,
    now_utc: datetime,
    total_rounds: int = FRIEND_CHALLENGE_TOTAL_ROUNDS,
) -> FriendChallengeSnapshot:
    access_type = await _resolve_friend_challenge_access_type(
        session,
        creator_user_id=creator_user_id,
        now_utc=now_utc,
    )
    challenge = await _create_friend_challenge_row(
        session,
        creator_user_id=creator_user_id,
        opponent_user_id=None,
        mode_code=mode_code,
        access_type=access_type,
        total_rounds=total_rounds,
        now_utc=now_utc,
    )
    await emit_analytics_event(
        session,
        event_type="friend_challenge_created",
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=creator_user_id,
        payload={
            "challenge_id": str(challenge.id),
            "mode_code": challenge.mode_code,
            "access_type": challenge.access_type,
            "total_rounds": challenge.total_rounds,
            "entrypoint": "standard",
            "expires_at": challenge.expires_at.isoformat(),
            "series_id": None,
            "series_game_number": challenge.series_game_number,
            "series_best_of": challenge.series_best_of,
        },
    )
    return _build_friend_challenge_snapshot(challenge)


async def create_friend_challenge_rematch(
    session: AsyncSession,
    *,
    initiator_user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
) -> FriendChallengeSnapshot:
    challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
    if challenge is None:
        raise FriendChallengeNotFoundError
    if _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
        await _emit_friend_challenge_expired_event(
            session,
            challenge=challenge,
            happened_at=now_utc,
            source=EVENT_SOURCE_BOT,
        )
    if challenge.status not in {"COMPLETED", "EXPIRED"}:
        raise FriendChallengeAccessError
    if initiator_user_id not in {
        challenge.creator_user_id,
        challenge.opponent_user_id,
    }:
        raise FriendChallengeAccessError

    opponent_user_id = _resolve_challenge_opponent_user_id(
        challenge=challenge,
        initiator_user_id=initiator_user_id,
    )

    series_id = challenge.series_id
    series_game_number = 1
    series_best_of = 1
    if series_id is not None and challenge.series_best_of > 1:
        series_challenges = await FriendChallengesRepo.list_by_series_id_for_update(
            session,
            series_id=series_id,
        )
        creator_wins, opponent_wins = _count_series_wins(
            series_challenges=series_challenges,
            creator_user_id=challenge.creator_user_id,
            opponent_user_id=challenge.opponent_user_id,
        )
        wins_needed = _series_wins_needed(best_of=challenge.series_best_of)
        max_wins = max(creator_wins, opponent_wins)
        max_game_number = max(
            (int(item.series_game_number) for item in series_challenges),
            default=int(challenge.series_game_number),
        )
        if max_wins < wins_needed and max_game_number < challenge.series_best_of:
            series_game_number = max_game_number + 1
            series_best_of = challenge.series_best_of
        else:
            series_id = None

    access_type = await _resolve_friend_challenge_access_type(
        session,
        creator_user_id=initiator_user_id,
        now_utc=now_utc,
    )
    rematch = await _create_friend_challenge_row(
        session,
        creator_user_id=initiator_user_id,
        opponent_user_id=opponent_user_id,
        mode_code=challenge.mode_code,
        access_type=access_type,
        total_rounds=challenge.total_rounds,
        now_utc=now_utc,
        series_id=series_id,
        series_game_number=series_game_number,
        series_best_of=series_best_of,
    )
    await emit_analytics_event(
        session,
        event_type="friend_challenge_created",
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=initiator_user_id,
        payload={
            "challenge_id": str(rematch.id),
            "mode_code": rematch.mode_code,
            "access_type": rematch.access_type,
            "total_rounds": rematch.total_rounds,
            "entrypoint": "rematch",
            "source_challenge_id": str(challenge_id),
            "expires_at": rematch.expires_at.isoformat(),
            "series_id": (str(rematch.series_id) if rematch.series_id is not None else None),
            "series_game_number": rematch.series_game_number,
            "series_best_of": rematch.series_best_of,
        },
    )
    await emit_analytics_event(
        session,
        event_type="friend_challenge_rematch_created",
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=initiator_user_id,
        payload={
            "challenge_id": str(rematch.id),
            "source_challenge_id": str(challenge_id),
            "opponent_user_id": opponent_user_id,
            "total_rounds": rematch.total_rounds,
            "expires_at": rematch.expires_at.isoformat(),
            "series_id": (str(rematch.series_id) if rematch.series_id is not None else None),
            "series_game_number": rematch.series_game_number,
            "series_best_of": rematch.series_best_of,
        },
    )
    return _build_friend_challenge_snapshot(rematch)
