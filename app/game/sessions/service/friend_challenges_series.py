from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.friend_challenges.constants import DUEL_STATUS_ACCEPTED, DUEL_TYPE_DIRECT
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError
from app.game.sessions.types import FriendChallengeSnapshot

from .friend_challenges_internal import (
    _build_friend_challenge_snapshot,
    _create_friend_challenge_row,
    _emit_friend_challenge_expired_event,
    _expire_friend_challenge_if_due,
    _resolve_friend_challenge_access_type,
)
from .friend_challenges_series_utils import (
    _count_series_wins,
    _resolve_challenge_opponent_user_id,
    _series_wins_needed,
)


async def create_friend_challenge_best_of_three(
    session: AsyncSession,
    *,
    initiator_user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
    best_of: int = 3,
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
    if challenge.status not in {"COMPLETED", "EXPIRED", "WALKOVER"}:
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
    resolved_best_of = max(1, int(best_of))

    access_type = await _resolve_friend_challenge_access_type(
        session,
        creator_user_id=initiator_user_id,
        now_utc=now_utc,
    )
    series_id = uuid4()
    duel = await _create_friend_challenge_row(
        session,
        creator_user_id=initiator_user_id,
        opponent_user_id=opponent_user_id,
        challenge_type=DUEL_TYPE_DIRECT,
        mode_code=challenge.mode_code,
        access_type=access_type,
        total_rounds=challenge.total_rounds,
        now_utc=now_utc,
        series_id=series_id,
        series_game_number=1,
        series_best_of=resolved_best_of,
        status=DUEL_STATUS_ACCEPTED,
    )
    await emit_analytics_event(
        session,
        event_type="friend_challenge_created",
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=initiator_user_id,
        payload={
            "challenge_id": str(duel.id),
            "mode_code": duel.mode_code,
            "access_type": duel.access_type,
            "total_rounds": duel.total_rounds,
            "entrypoint": "best_of_series",
            "source_challenge_id": str(challenge_id),
            "series_id": str(series_id),
            "series_game_number": duel.series_game_number,
            "series_best_of": duel.series_best_of,
            "expires_at": duel.expires_at.isoformat(),
        },
    )
    await emit_analytics_event(
        session,
        event_type="friend_challenge_series_started",
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=initiator_user_id,
        payload={
            "challenge_id": str(duel.id),
            "source_challenge_id": str(challenge_id),
            "opponent_user_id": opponent_user_id,
            "series_id": str(series_id),
            "series_game_number": duel.series_game_number,
            "series_best_of": duel.series_best_of,
        },
    )
    return _build_friend_challenge_snapshot(duel)


async def create_friend_challenge_series_next_game(
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
    if challenge.status not in {"COMPLETED", "EXPIRED", "WALKOVER"}:
        raise FriendChallengeAccessError
    if initiator_user_id not in {
        challenge.creator_user_id,
        challenge.opponent_user_id,
    }:
        raise FriendChallengeAccessError
    if challenge.series_id is None or challenge.series_best_of <= 1:
        raise FriendChallengeAccessError

    series_challenges = await FriendChallengesRepo.list_by_series_id_for_update(
        session,
        series_id=challenge.series_id,
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
    if max_wins >= wins_needed or max_game_number >= challenge.series_best_of:
        raise FriendChallengeAccessError

    opponent_user_id = _resolve_challenge_opponent_user_id(
        challenge=challenge,
        initiator_user_id=initiator_user_id,
    )
    access_type = await _resolve_friend_challenge_access_type(
        session,
        creator_user_id=initiator_user_id,
        now_utc=now_utc,
    )
    duel = await _create_friend_challenge_row(
        session,
        creator_user_id=initiator_user_id,
        opponent_user_id=opponent_user_id,
        challenge_type=DUEL_TYPE_DIRECT,
        mode_code=challenge.mode_code,
        access_type=access_type,
        total_rounds=challenge.total_rounds,
        now_utc=now_utc,
        series_id=challenge.series_id,
        series_game_number=max_game_number + 1,
        series_best_of=challenge.series_best_of,
        status=DUEL_STATUS_ACCEPTED,
    )
    await emit_analytics_event(
        session,
        event_type="friend_challenge_created",
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=initiator_user_id,
        payload={
            "challenge_id": str(duel.id),
            "mode_code": duel.mode_code,
            "access_type": duel.access_type,
            "total_rounds": duel.total_rounds,
            "entrypoint": "best_of_series_next_game",
            "source_challenge_id": str(challenge_id),
            "series_id": str(duel.series_id),
            "series_game_number": duel.series_game_number,
            "series_best_of": duel.series_best_of,
            "expires_at": duel.expires_at.isoformat(),
        },
    )
    await emit_analytics_event(
        session,
        event_type="friend_challenge_series_game_created",
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=initiator_user_id,
        payload={
            "challenge_id": str(duel.id),
            "source_challenge_id": str(challenge_id),
            "opponent_user_id": opponent_user_id,
            "series_id": str(duel.series_id),
            "series_game_number": duel.series_game_number,
            "series_best_of": duel.series_best_of,
        },
    )
    return _build_friend_challenge_snapshot(duel)
