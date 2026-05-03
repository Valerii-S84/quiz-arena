from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.arena_duels.constants import ARENA_REVANCHE_NOTIFICATION_TYPE
from app.game.arena_duels.errors import ArenaDuelAccessError
from app.game.arena_duels.revanche_types import ArenaRevancheContext
from app.game.duels.constants import DUEL_QUESTION_COUNT
from app.game.friend_challenges.constants import DUEL_STATUS_ACCEPTED, DUEL_TYPE_DIRECT
from app.game.sessions.service.friend_challenges_internal import (
    _build_friend_challenge_snapshot,
    _create_friend_challenge_row,
)
from app.game.sessions.service.friend_challenges_question_plan import select_duel_question_ids
from app.game.sessions.types import FriendChallengeSnapshot


def build_arena_revanche_payload(
    *,
    context: ArenaRevancheContext,
    challenge_id: UUID | None = None,
    access_type: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "arena_duel_id": str(context.arena_duel_id),
        "revanche_sender_id": context.sender_user_id,
        "revanche_receiver_id": context.receiver_user_id,
        "source_attempt_id": str(context.source_attempt_id),
        "notification_type": ARENA_REVANCHE_NOTIFICATION_TYPE,
    }
    if challenge_id is not None:
        payload["challenge_id"] = str(challenge_id)
    if access_type is not None:
        payload["access_type"] = access_type
    return payload


async def create_revanche_friend_challenge(
    session: AsyncSession,
    *,
    context: ArenaRevancheContext,
    access_type: str,
    now_utc: datetime,
) -> FriendChallengeSnapshot:
    challenge_id = uuid4()
    question_ids = await select_duel_question_ids(
        session,
        mode_code=context.mode_code,
        total_rounds=DUEL_QUESTION_COUNT,
        now_utc=now_utc,
        challenge_seed=str(challenge_id),
    )
    challenge = await _create_friend_challenge_row(
        session,
        challenge_id=challenge_id,
        creator_user_id=context.sender_user_id,
        opponent_user_id=context.receiver_user_id,
        challenge_type=DUEL_TYPE_DIRECT,
        mode_code=context.mode_code,
        access_type=access_type,
        total_rounds=DUEL_QUESTION_COUNT,
        now_utc=now_utc,
        question_ids=question_ids,
        status=DUEL_STATUS_ACCEPTED,
    )
    return _build_friend_challenge_snapshot(challenge)


async def load_revanche_friend_challenge(
    session: AsyncSession,
    *,
    challenge_id: UUID,
    context: ArenaRevancheContext,
) -> FriendChallengeSnapshot:
    challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
    if challenge is None:
        raise ArenaDuelAccessError
    if (
        challenge.creator_user_id != context.sender_user_id
        or challenge.opponent_user_id != context.receiver_user_id
        or challenge.challenge_type != DUEL_TYPE_DIRECT
        or challenge.mode_code != context.mode_code
    ):
        raise ArenaDuelAccessError
    return _build_friend_challenge_snapshot(challenge)


async def delete_revanche_friend_challenge(
    session: AsyncSession,
    *,
    challenge_id: UUID,
    context: ArenaRevancheContext,
) -> None:
    challenge = await FriendChallengesRepo.get_by_id_for_update(session, challenge_id)
    if challenge is None:
        return
    if (
        challenge.creator_user_id != context.sender_user_id
        or challenge.opponent_user_id != context.receiver_user_id
        or challenge.challenge_type != DUEL_TYPE_DIRECT
        or challenge.mode_code != context.mode_code
    ):
        raise ArenaDuelAccessError
    await session.delete(challenge)
    await session.flush()


def ensure_source_attempt_can_receive_revanche(
    *,
    sender_user_id: int,
    receiver_user_id: int,
    source_attempt_ready: bool,
) -> None:
    if sender_user_id == receiver_user_id:
        raise ArenaDuelAccessError
    if not source_attempt_ready:
        raise ArenaDuelAccessError
