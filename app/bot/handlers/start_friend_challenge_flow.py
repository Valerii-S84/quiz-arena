from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from aiogram.types import InlineKeyboardMarkup

from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_back_keyboard,
    build_friend_challenge_next_keyboard,
    build_friend_open_taken_keyboard,
)
from app.bot.keyboards.home import build_home_keyboard
from app.bot.keyboards.quiz import build_quiz_keyboard
from app.bot.texts.de import TEXTS_DE
from app.core.config import get_settings
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)
from app.game.sessions.types import FriendChallengeRoundStartResult, FriendChallengeSnapshot


@dataclass(slots=True)
class OutgoingStartMessage:
    text: str
    reply_markup: InlineKeyboardMarkup
    parse_mode: str | None = None
    photo: str | None = None


@dataclass(slots=True)
class StartFriendChallengeHandlingResult:
    handled: bool
    messages: list[OutgoingStartMessage] = field(default_factory=list)
    notify_creator: bool = False
    notify_challenge: FriendChallengeSnapshot | None = None
    notify_joiner_user_id: int | None = None


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


def _error_key_for_friend_challenge_start_failure(
    *,
    duel_challenge_id: str | None,
    error: Exception,
) -> str:
    if isinstance(error, FriendChallengeExpiredError):
        return "msg.friend.challenge.expired"
    if isinstance(error, FriendChallengeFullError):
        return (
            "msg.friend.challenge.open.taken"
            if duel_challenge_id is not None
            else "msg.friend.challenge.full"
        )
    return "msg.friend.challenge.invalid"


def _build_start_friend_challenge_error_result(
    *,
    challenge_error_key: str,
) -> StartFriendChallengeHandlingResult:
    reply_markup = (
        build_friend_open_taken_keyboard()
        if challenge_error_key == "msg.friend.challenge.open.taken"
        else build_home_keyboard()
    )
    return StartFriendChallengeHandlingResult(
        handled=True,
        messages=[
            OutgoingStartMessage(
                text=TEXTS_DE[challenge_error_key],
                reply_markup=reply_markup,
            )
        ],
    )


def _build_friend_challenge_summary_lines(
    *,
    challenge_start,
    snapshot,
    opponent_label: str,
    now_utc: datetime,
    build_friend_plan_text,
    build_friend_score_text,
    build_friend_ttl_text,
) -> list[str]:
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
    return summary_lines


def _build_welcome_start_message(
    *,
    challenge_start,
    opponent_label: str,
) -> OutgoingStartMessage | None:
    welcome_image_file_id = get_settings().resolved_welcome_image_file_id
    if not welcome_image_file_id:
        return None
    return OutgoingStartMessage(
        text=(
            f"⚔️ {opponent_label} fordert dich heraus!\n"
            f"Format: {challenge_start.snapshot.total_rounds} Fragen • Deutsch lernen"
        ),
        reply_markup=build_friend_challenge_next_keyboard(
            challenge_id=str(challenge_start.snapshot.challenge_id)
        ),
        photo=welcome_image_file_id,
    )


def _build_summary_start_message(*, summary_lines: list[str]) -> OutgoingStartMessage:
    return OutgoingStartMessage(
        text="\n".join(summary_lines),
        reply_markup=build_friend_challenge_back_keyboard(),
    )


def _build_question_start_message(
    *,
    challenge_start,
    snapshot,
    build_question_text,
) -> OutgoingStartMessage | None:
    if challenge_start.start_result is None:
        return None

    question_text = build_question_text(
        source="FRIEND_CHALLENGE",
        snapshot_free_energy=snapshot.free_energy,
        snapshot_paid_energy=snapshot.paid_energy,
        start_result=challenge_start.start_result,
    )
    return OutgoingStartMessage(
        text=question_text,
        reply_markup=build_quiz_keyboard(
            session_id=str(challenge_start.start_result.session.session_id),
            options=challenge_start.start_result.session.options,
        ),
        parse_mode="HTML",
    )


def _build_start_friend_challenge_success_result(
    *,
    challenge_start,
    challenge_joined_now: bool,
    snapshot,
    opponent_label: str,
    now_utc: datetime,
    build_friend_plan_text,
    build_friend_score_text,
    build_friend_ttl_text,
    build_question_text,
) -> StartFriendChallengeHandlingResult:
    summary_lines = _build_friend_challenge_summary_lines(
        challenge_start=challenge_start,
        snapshot=snapshot,
        opponent_label=opponent_label,
        now_utc=now_utc,
        build_friend_plan_text=build_friend_plan_text,
        build_friend_score_text=build_friend_score_text,
        build_friend_ttl_text=build_friend_ttl_text,
    )
    outgoing_messages: list[OutgoingStartMessage] = []
    welcome_message = _build_welcome_start_message(
        challenge_start=challenge_start,
        opponent_label=opponent_label,
    )
    if welcome_message is not None:
        outgoing_messages.append(welcome_message)
    outgoing_messages.append(_build_summary_start_message(summary_lines=summary_lines))
    question_message = _build_question_start_message(
        challenge_start=challenge_start,
        snapshot=snapshot,
        build_question_text=build_question_text,
    )
    if question_message is not None:
        outgoing_messages.append(question_message)
    return StartFriendChallengeHandlingResult(
        handled=True,
        messages=outgoing_messages,
        notify_creator=challenge_joined_now,
        notify_challenge=challenge_start.snapshot if challenge_joined_now else None,
        notify_joiner_user_id=snapshot.user_id if challenge_joined_now else None,
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
        return _build_start_friend_challenge_error_result(
            challenge_error_key=_error_key_for_friend_challenge_start_failure(
                duel_challenge_id=duel_challenge_id,
                error=error,
            )
        )

    opponent_label = await resolve_opponent_label(
        challenge=started_payload.challenge_start.snapshot,
        user_id=snapshot.user_id,
    )
    return _build_start_friend_challenge_success_result(
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
