from __future__ import annotations

import logging

from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery

from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_back_keyboard,
    build_friend_challenge_share_keyboard,
)
from app.bot.texts.de import TEXTS_DE
from app.core.config import get_settings
from app.game.sessions.types import FriendChallengeSnapshot


async def send_friend_challenge_invite(
    callback: CallbackQuery,
    *,
    challenge: FriendChallengeSnapshot,
    build_friend_invite_link,
    get_settings_factory=get_settings,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    invite_link = await build_friend_invite_link(callback, challenge_id=str(challenge.challenge_id))
    if invite_link is None:
        await callback.message.answer(
            TEXTS_DE["msg.friend.challenge.created.fallback"].format(
                invite_token=challenge.invite_token
            ),
            reply_markup=build_friend_challenge_back_keyboard(),
        )
        return
    welcome_image_file_id = get_settings_factory().resolved_welcome_image_file_id
    photo_sent = False
    share_keyboard = build_friend_challenge_share_keyboard(
        invite_link=invite_link,
        challenge_id=str(challenge.challenge_id),
    )
    if welcome_image_file_id:
        bot = callback.bot
        assert bot is not None
        try:
            await bot.send_photo(
                chat_id=callback.from_user.id,
                photo=welcome_image_file_id,
                caption=TEXTS_DE["msg.friend.challenge.invite.caption"],
                parse_mode="HTML",
                reply_markup=share_keyboard,
            )
            photo_sent = True
        except TelegramAPIError as exc:
            logging.getLogger(__name__).error(
                "send_photo failed for friend challenge: user=%s file_id=%s error=%s",
                callback.from_user.id,
                welcome_image_file_id,
                exc,
            )
    if not photo_sent:
        await callback.message.answer(
            TEXTS_DE["msg.friend.challenge.invite.caption"],
            parse_mode="HTML",
            reply_markup=share_keyboard,
        )
