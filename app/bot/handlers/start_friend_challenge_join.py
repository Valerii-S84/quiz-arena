from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)

from .start_friend_challenge_models import StartFriendChallengePayloadContext


@dataclass(frozen=True, slots=True)
class StartedFriendChallenge:
    challenge_start: Any
    joined_now: bool


async def join_and_start_friend_challenge(
    context: StartFriendChallengePayloadContext,
) -> tuple[StartedFriendChallenge | None, str | None]:
    try:
        return await _join_and_start(context), None
    except (
        FriendChallengeNotFoundError,
        FriendChallengeCompletedError,
        FriendChallengeAccessError,
    ):
        return None, "msg.friend.challenge.invalid"
    except FriendChallengeExpiredError:
        return None, "msg.friend.challenge.expired"
    except FriendChallengeFullError:
        return None, _full_challenge_error_key(context)


async def _join_and_start(context: StartFriendChallengePayloadContext) -> StartedFriendChallenge:
    join_result = await _join_friend_challenge(context)
    if join_result is None:
        raise FriendChallengeNotFoundError

    challenge = join_result.snapshot
    challenge_start = await context.game_session_service.start_friend_challenge_round(
        context.session,
        user_id=context.snapshot.user_id,
        challenge_id=challenge.challenge_id,
        idempotency_key=(f"start:friend:join:{challenge.challenge_id}:{context.start_message_id}"),
        now_utc=context.now_utc,
    )
    return StartedFriendChallenge(
        challenge_start=challenge_start,
        joined_now=join_result.joined_now,
    )


async def _join_friend_challenge(context: StartFriendChallengePayloadContext):
    if context.duel_challenge_id is not None:
        return await _join_friend_challenge_by_id(context)
    return await context.game_session_service.join_friend_challenge_by_token(
        context.session,
        user_id=context.snapshot.user_id,
        invite_token=context.friend_invite_token or "",
        now_utc=context.now_utc,
    )


async def _join_friend_challenge_by_id(context: StartFriendChallengePayloadContext):
    try:
        parsed_duel_id = UUID(context.duel_challenge_id or "")
    except ValueError as exc:
        raise FriendChallengeNotFoundError from exc
    return await context.game_session_service.join_friend_challenge_by_id(
        context.session,
        user_id=context.snapshot.user_id,
        challenge_id=parsed_duel_id,
        now_utc=context.now_utc,
    )


def _full_challenge_error_key(context: StartFriendChallengePayloadContext) -> str:
    if context.duel_challenge_id is not None:
        return "msg.friend.challenge.open.taken"
    return "msg.friend.challenge.full"
