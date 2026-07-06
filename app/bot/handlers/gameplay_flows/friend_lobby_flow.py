from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

from aiogram.types import CallbackQuery

from app.bot.keyboards.duels import build_friend_duel_keyboard
from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_limit_keyboard,
    build_friend_challenge_share_confirmed_keyboard,
)
from app.bot.texts.de import TEXTS_DE
from app.core.config import get_settings
from app.game.friend_challenges.constants import DUEL_TYPE_DIRECT
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeLimitExceededError,
    FriendChallengeNotFoundError,
    FriendChallengePaymentRequiredError,
)

from .friend_lobby_invite_flow import send_friend_challenge_invite as _send_friend_challenge_invite
from .friend_my_duels_flow import handle_friend_my_duels as handle_friend_my_duels


async def handle_friend_challenge_type_selected(
    callback: CallbackQuery,
    *,
    friend_create_type_re,
) -> None:
    if callback.data is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    matched = friend_create_type_re.match(callback.data)
    if matched is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    del matched
    await callback.message.answer(
        TEXTS_DE["msg.duels.friend"],
        reply_markup=build_friend_duel_keyboard(),
    )
    await callback.answer()


async def handle_friend_challenge_create_selected(
    callback: CallbackQuery,
    *,
    session_local,
    user_onboarding_service,
    game_session_service,
    parse_friend_create_format,
    build_friend_invite_link,
    build_friend_plan_text,
    build_friend_ttl_text,
) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    parsed = parse_friend_create_format(callback.data)
    if parsed is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    _, selected_rounds = parsed
    now_utc = datetime.now(timezone.utc)
    async with session_local.begin() as session:
        onboarding = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        try:
            challenge = await game_session_service.create_friend_challenge(
                session,
                creator_user_id=onboarding.user_id,
                mode_code="QUICK_MIX_A1A2",
                now_utc=now_utc,
                challenge_type=DUEL_TYPE_DIRECT,
                total_rounds=selected_rounds,
            )
        except (FriendChallengePaymentRequiredError, FriendChallengeLimitExceededError):
            await callback.message.answer(
                TEXTS_DE["msg.friend.challenge.limit.reached"],
                reply_markup=build_friend_challenge_limit_keyboard(
                    paywall_context="friend_create_limit"
                ),
            )
            await callback.answer()
            return
    await send_friend_challenge_invite(
        callback,
        challenge=challenge,
        build_friend_invite_link=build_friend_invite_link,
    )
    await callback.answer()


async def send_friend_challenge_invite(
    callback: CallbackQuery,
    *,
    challenge,
    build_friend_invite_link,
) -> None:
    await _send_friend_challenge_invite(
        callback,
        challenge=challenge,
        build_friend_invite_link=build_friend_invite_link,
        get_settings_factory=get_settings,
    )


async def handle_friend_challenge_invite_sent(
    callback: CallbackQuery,
    *,
    friend_invite_sent_re,
    parse_uuid_callback,
) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    if not hasattr(callback.message, "edit_reply_markup"):
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    challenge_id = parse_uuid_callback(pattern=friend_invite_sent_re, callback_data=callback.data)
    if challenge_id is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await cast(Any, callback.message).edit_reply_markup(
        reply_markup=build_friend_challenge_share_confirmed_keyboard(challenge_id=str(challenge_id))
    )
    await callback.answer(TEXTS_DE["msg.friend.challenge.invite.waiting"])


async def handle_friend_copy_link(
    callback: CallbackQuery,
    *,
    friend_copy_link_re,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    game_session_service,
    build_friend_invite_link,
) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    del build_friend_invite_link
    challenge_id = parse_uuid_callback(pattern=friend_copy_link_re, callback_data=callback.data)
    if challenge_id is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    now_utc = datetime.now(timezone.utc)
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        try:
            await game_session_service.get_friend_challenge_snapshot_for_user(
                session,
                user_id=snapshot.user_id,
                challenge_id=challenge_id,
                now_utc=now_utc,
            )
        except (FriendChallengeNotFoundError, FriendChallengeAccessError):
            await callback.message.answer(TEXTS_DE["msg.friend.challenge.invalid"])
            await callback.answer()
            return
    await callback.answer(TEXTS_DE["msg.friend.challenge.link.share.inline"])
