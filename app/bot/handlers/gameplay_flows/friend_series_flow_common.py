from __future__ import annotations

from typing import Any

from aiogram.types import CallbackQuery

from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_limit_keyboard,
    build_friend_challenge_next_keyboard,
)
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import (
    FriendChallengeLimitExceededError,
    FriendChallengePaymentRequiredError,
)


def build_series_reply_markup(*, challenge_id: str):
    return build_friend_challenge_next_keyboard(challenge_id=challenge_id)


async def handle_series_flow_error(
    *, callback: CallbackQuery, message: Any, exc: Exception
) -> None:
    if isinstance(exc, (FriendChallengePaymentRequiredError, FriendChallengeLimitExceededError)):
        await message.answer(
            TEXTS_DE["msg.friend.challenge.limit.reached"],
            reply_markup=build_friend_challenge_limit_keyboard(),
        )
    else:
        await message.answer(
            TEXTS_DE["msg.friend.challenge.invalid"],
            reply_markup=build_home_keyboard(),
        )
    await callback.answer()


__all__ = ["build_series_reply_markup", "handle_series_flow_error"]
