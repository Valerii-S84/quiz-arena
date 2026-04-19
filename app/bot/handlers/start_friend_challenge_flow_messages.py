from __future__ import annotations

from datetime import datetime

from app.bot.handlers.start_friend_challenge_flow_message_types import (
    OutgoingStartMessage,
    StartFriendChallengeHandlingResult,
    build_start_friend_challenge_error_result,
    error_key_for_friend_challenge_start_failure,
)
from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_back_keyboard,
    build_friend_challenge_next_keyboard,
)
from app.bot.keyboards.quiz import build_quiz_keyboard
from app.bot.texts.de import TEXTS_DE
from app.core.config import get_settings

__all__ = [
    "OutgoingStartMessage",
    "StartFriendChallengeHandlingResult",
    "error_key_for_friend_challenge_start_failure",
    "build_start_friend_challenge_error_result",
    "build_start_friend_challenge_success_result",
]


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


def build_start_friend_challenge_success_result(
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
