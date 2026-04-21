from __future__ import annotations

from app.bot.handlers.start_friend_challenge_flow_message_types import (
    OutgoingStartMessage,
    StartFriendChallengeHandlingResult,
    build_start_friend_challenge_error_result,
    error_key_for_friend_challenge_start_failure,
)
from app.bot.keyboards.friend_challenge import build_friend_challenge_onboarding_keyboard
from app.bot.texts.de import TEXTS_DE
from app.core.config import get_settings

__all__ = [
    "OutgoingStartMessage",
    "StartFriendChallengeHandlingResult",
    "error_key_for_friend_challenge_start_failure",
    "build_start_friend_challenge_error_result",
    "build_start_friend_challenge_success_result",
]


def _build_onboarding_start_message(
    *,
    challenge_snapshot,
    opponent_label: str,
) -> OutgoingStartMessage:
    onboarding_message = OutgoingStartMessage(
        text=TEXTS_DE["msg.friend.challenge.onboarding"].format(challenger_name=opponent_label),
        reply_markup=build_friend_challenge_onboarding_keyboard(
            challenge_id=str(challenge_snapshot.challenge_id)
        ),
    )
    welcome_image_file_id = get_settings().resolved_welcome_image_file_id
    if welcome_image_file_id:
        onboarding_message.photo = welcome_image_file_id
    return onboarding_message


def build_start_friend_challenge_success_result(
    *,
    challenge_snapshot,
    challenge_joined_now: bool,
    joiner_user_id: int,
    opponent_label: str,
) -> StartFriendChallengeHandlingResult:
    return StartFriendChallengeHandlingResult(
        handled=True,
        messages=[
            _build_onboarding_start_message(
                challenge_snapshot=challenge_snapshot,
                opponent_label=opponent_label,
            )
        ],
        notify_creator=challenge_joined_now,
        notify_challenge=challenge_snapshot if challenge_joined_now else None,
        notify_joiner_user_id=joiner_user_id if challenge_joined_now else None,
    )
