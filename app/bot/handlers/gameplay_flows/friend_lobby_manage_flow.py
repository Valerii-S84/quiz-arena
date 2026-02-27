from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import CallbackQuery

from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_back_keyboard,
    build_friend_challenge_share_keyboard,
)
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeLimitExceededError,
    FriendChallengeNotFoundError,
    FriendChallengePaymentRequiredError,
)


async def handle_friend_open_repost(
    callback: CallbackQuery,
    *,
    friend_open_repost_re,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    game_session_service,
    build_friend_invite_link,
    build_friend_plan_text,
    build_friend_ttl_text,
) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    challenge_id = parse_uuid_callback(pattern=friend_open_repost_re, callback_data=callback.data)
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
            repost = await game_session_service.repost_friend_challenge_as_open(
                session,
                user_id=snapshot.user_id,
                challenge_id=challenge_id,
                now_utc=now_utc,
            )
        except (
            FriendChallengeNotFoundError,
            FriendChallengeAccessError,
        ):
            await callback.message.answer(
                TEXTS_DE["msg.friend.challenge.invalid"],
                reply_markup=build_friend_challenge_back_keyboard(),
            )
            await callback.answer()
            return
        except (FriendChallengePaymentRequiredError, FriendChallengeLimitExceededError):
            await callback.message.answer(TEXTS_DE["msg.friend.challenge.limit.reached"])
            await callback.answer()
            return

    invite_link = await build_friend_invite_link(callback, challenge_id=str(repost.challenge_id))
    if invite_link is None:
        await callback.message.answer(TEXTS_DE["msg.system.error"])
        await callback.answer()
        return
    body_lines = [
        TEXTS_DE["msg.friend.challenge.created"],
        build_friend_plan_text(total_rounds=repost.total_rounds),
        TEXTS_DE["msg.friend.challenge.created.short"],
    ]
    ttl_text = build_friend_ttl_text(challenge=repost, now_utc=now_utc)
    if ttl_text is not None:
        body_lines.append(ttl_text)
    await callback.message.answer(
        "\n".join(body_lines),
        reply_markup=build_friend_challenge_share_keyboard(
            invite_link=invite_link,
            challenge_id=str(repost.challenge_id),
            total_rounds=repost.total_rounds,
        ),
    )
    await callback.answer()


async def handle_friend_delete(
    callback: CallbackQuery,
    *,
    friend_delete_re,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    game_session_service,
) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    challenge_id = parse_uuid_callback(pattern=friend_delete_re, callback_data=callback.data)
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
            await game_session_service.cancel_friend_challenge_by_creator(
                session,
                user_id=snapshot.user_id,
                challenge_id=challenge_id,
                now_utc=now_utc,
            )
        except (FriendChallengeNotFoundError, FriendChallengeAccessError):
            await callback.message.answer(
                TEXTS_DE["msg.friend.challenge.invalid"],
                reply_markup=build_friend_challenge_back_keyboard(),
            )
            await callback.answer()
            return

    await callback.message.answer(
        TEXTS_DE["msg.friend.challenge.deleted"],
        reply_markup=build_friend_challenge_back_keyboard(),
    )
    await callback.answer()
