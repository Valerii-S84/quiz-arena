from __future__ import annotations

from dataclasses import dataclass, field

from aiogram.types import InlineKeyboardMarkup

from app.bot.keyboards.friend_challenge import build_friend_open_taken_keyboard
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import FriendChallengeExpiredError, FriendChallengeFullError
from app.game.sessions.types import FriendChallengeSnapshot


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


def error_key_for_friend_challenge_start_failure(
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


def build_start_friend_challenge_error_result(
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
