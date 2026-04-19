from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.bot.handlers import start_friend_challenge_flow_messages
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)
from app.game.sessions.types import FriendChallengeRoundStartResult

OutgoingStartMessage = start_friend_challenge_flow_messages.OutgoingStartMessage
StartFriendChallengeHandlingResult = (
    start_friend_challenge_flow_messages.StartFriendChallengeHandlingResult
)


@dataclass(slots=True)
class _StartedFriendChallengePayload:
    challenge_start: FriendChallengeRoundStartResult
    challenge_joined_now: bool


def _parse_duel_challenge_id(duel_challenge_id: str) -> UUID:
    try:
        return UUID(duel_challenge_id)
    except ValueError as exc:
        raise FriendChallengeNotFoundError from exc


async def _join_friend_challenge_for_start(
    *,
    session,
    snapshot,
    friend_invite_token: str | None,
    duel_challenge_id: str | None,
    now_utc: datetime,
    game_session_service,
):
    if duel_challenge_id is not None:
        return await game_session_service.join_friend_challenge_by_id(
            session,
            user_id=snapshot.user_id,
            challenge_id=_parse_duel_challenge_id(duel_challenge_id),
            now_utc=now_utc,
        )
    return await game_session_service.join_friend_challenge_by_token(
        session,
        user_id=snapshot.user_id,
        invite_token=friend_invite_token or "",
        now_utc=now_utc,
    )


async def _start_joined_friend_challenge(
    *,
    session,
    snapshot,
    friend_invite_token: str | None,
    duel_challenge_id: str | None,
    start_message_id: int,
    now_utc: datetime,
    game_session_service,
) -> _StartedFriendChallengePayload:
    join_result = await _join_friend_challenge_for_start(
        session=session,
        snapshot=snapshot,
        friend_invite_token=friend_invite_token,
        duel_challenge_id=duel_challenge_id,
        now_utc=now_utc,
        game_session_service=game_session_service,
    )
    if join_result is None:
        raise FriendChallengeNotFoundError

    challenge_start = await game_session_service.start_friend_challenge_round(
        session,
        user_id=snapshot.user_id,
        challenge_id=join_result.snapshot.challenge_id,
        idempotency_key=f"start:friend:join:{join_result.snapshot.challenge_id}:{start_message_id}",
        now_utc=now_utc,
    )
    return _StartedFriendChallengePayload(
        challenge_start=challenge_start,
        challenge_joined_now=join_result.joined_now,
    )


async def handle_start_friend_challenge_payload(
    *,
    session,
    now_utc: datetime,
    snapshot,
    friend_invite_token: str | None,
    duel_challenge_id: str | None,
    start_message_id: int,
    game_session_service,
    resolve_opponent_label,
    build_friend_plan_text,
    build_friend_score_text,
    build_friend_ttl_text,
    build_question_text,
) -> StartFriendChallengeHandlingResult | None:
    if friend_invite_token is None and duel_challenge_id is None:
        return None

    try:
        started_payload = await _start_joined_friend_challenge(
            session=session,
            snapshot=snapshot,
            friend_invite_token=friend_invite_token,
            duel_challenge_id=duel_challenge_id,
            start_message_id=start_message_id,
            now_utc=now_utc,
            game_session_service=game_session_service,
        )
    except (
        FriendChallengeNotFoundError,
        FriendChallengeCompletedError,
        FriendChallengeAccessError,
        FriendChallengeExpiredError,
        FriendChallengeFullError,
    ) as error:
        return start_friend_challenge_flow_messages.build_start_friend_challenge_error_result(
            challenge_error_key=start_friend_challenge_flow_messages.error_key_for_friend_challenge_start_failure(
                duel_challenge_id=duel_challenge_id,
                error=error,
            )
        )

    opponent_label = await resolve_opponent_label(
        challenge=started_payload.challenge_start.snapshot,
        user_id=snapshot.user_id,
    )
    return start_friend_challenge_flow_messages.build_start_friend_challenge_success_result(
        challenge_start=started_payload.challenge_start,
        challenge_joined_now=started_payload.challenge_joined_now,
        snapshot=snapshot,
        opponent_label=opponent_label,
        now_utc=now_utc,
        build_friend_plan_text=build_friend_plan_text,
        build_friend_score_text=build_friend_score_text,
        build_friend_ttl_text=build_friend_ttl_text,
        build_question_text=build_question_text,
    )
