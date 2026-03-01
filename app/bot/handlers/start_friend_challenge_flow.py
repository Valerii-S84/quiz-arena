from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from aiogram.types import InlineKeyboardMarkup

from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_back_keyboard,
    build_friend_open_taken_keyboard,
)
from app.bot.keyboards.home import build_home_keyboard
from app.bot.keyboards.quiz import build_quiz_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)
from app.game.sessions.types import FriendChallengeSnapshot


@dataclass(slots=True)
class OutgoingStartMessage:
    text: str
    reply_markup: InlineKeyboardMarkup
    parse_mode: str | None = None


@dataclass(slots=True)
class StartFriendChallengeHandlingResult:
    handled: bool
    messages: list[OutgoingStartMessage] = field(default_factory=list)
    notify_creator: bool = False
    notify_challenge: FriendChallengeSnapshot | None = None
    notify_joiner_user_id: int | None = None


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

    challenge_start = None
    challenge_joined_now = False
    challenge_error_key: str | None = None

    try:
        if duel_challenge_id is not None:
            try:
                parsed_duel_id = UUID(duel_challenge_id)
            except ValueError:
                challenge_error_key = "msg.friend.challenge.invalid"
                join_result = None
            else:
                join_result = await game_session_service.join_friend_challenge_by_id(
                    session,
                    user_id=snapshot.user_id,
                    challenge_id=parsed_duel_id,
                    now_utc=now_utc,
                )
        else:
            join_result = await game_session_service.join_friend_challenge_by_token(
                session,
                user_id=snapshot.user_id,
                invite_token=friend_invite_token or "",
                now_utc=now_utc,
            )
        if join_result is None:
            raise FriendChallengeNotFoundError
        challenge = join_result.snapshot
        challenge_joined_now = join_result.joined_now
        challenge_start = await game_session_service.start_friend_challenge_round(
            session,
            user_id=snapshot.user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key=f"start:friend:join:{challenge.challenge_id}:{start_message_id}",
            now_utc=now_utc,
        )
    except (
        FriendChallengeNotFoundError,
        FriendChallengeCompletedError,
        FriendChallengeAccessError,
    ):
        challenge_error_key = "msg.friend.challenge.invalid"
    except FriendChallengeExpiredError:
        challenge_error_key = "msg.friend.challenge.expired"
    except FriendChallengeFullError:
        challenge_error_key = (
            "msg.friend.challenge.open.taken"
            if duel_challenge_id is not None
            else "msg.friend.challenge.full"
        )

    if challenge_error_key is not None or challenge_start is None:
        reply_markup = (
            build_friend_open_taken_keyboard()
            if challenge_error_key == "msg.friend.challenge.open.taken"
            else build_home_keyboard()
        )
        return StartFriendChallengeHandlingResult(
            handled=True,
            messages=[
                OutgoingStartMessage(
                    text=TEXTS_DE[challenge_error_key or "msg.friend.challenge.invalid"],
                    reply_markup=reply_markup,
                )
            ],
        )

    opponent_label = await resolve_opponent_label(
        challenge=challenge_start.snapshot,
        user_id=snapshot.user_id,
    )
    summary_lines = [
        TEXTS_DE["msg.friend.challenge.joined"],
        TEXTS_DE["msg.friend.challenge.with"].format(opponent_label=opponent_label),
        build_friend_plan_text(total_rounds=challenge_start.snapshot.total_rounds),
        TEXTS_DE["msg.friend.challenge.play.instant"].format(
            total_rounds=challenge_start.snapshot.total_rounds
        ),
        build_friend_score_text(
            challenge=challenge_start.snapshot,
            user_id=snapshot.user_id,
            opponent_label=opponent_label,
        ),
    ]
    ttl_text = build_friend_ttl_text(challenge=challenge_start.snapshot, now_utc=now_utc)
    if ttl_text is not None:
        summary_lines.append(ttl_text)
    if challenge_start.waiting_for_opponent:
        summary_lines.append(TEXTS_DE["msg.friend.challenge.waiting"])
    if challenge_start.already_answered_current_round:
        summary_lines.append(TEXTS_DE["msg.friend.challenge.round.already.answered"])
    outgoing_messages = [
        OutgoingStartMessage(
            text="\n".join(summary_lines),
            reply_markup=build_friend_challenge_back_keyboard(),
        )
    ]
    if challenge_start.start_result is not None:
        question_text = build_question_text(
            source="FRIEND_CHALLENGE",
            snapshot_free_energy=snapshot.free_energy,
            snapshot_paid_energy=snapshot.paid_energy,
            start_result=challenge_start.start_result,
        )
        outgoing_messages.append(
            OutgoingStartMessage(
                text=question_text,
                reply_markup=build_quiz_keyboard(
                    session_id=str(challenge_start.start_result.session.session_id),
                    options=challenge_start.start_result.session.options,
                ),
                parse_mode="HTML",
            )
        )
    return StartFriendChallengeHandlingResult(
        handled=True,
        messages=outgoing_messages,
        notify_creator=challenge_joined_now,
        notify_challenge=challenge_start.snapshot if challenge_joined_now else None,
        notify_joiner_user_id=snapshot.user_id if challenge_joined_now else None,
    )
