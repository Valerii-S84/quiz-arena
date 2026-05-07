from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.friend_lobby_flow import send_friend_challenge_invite
from app.bot.keyboards.duels import build_arena_back_keyboard
from app.bot.keyboards.friend_challenge import build_friend_challenge_limit_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeLimitExceededError,
    FriendChallengePaymentRequiredError,
)


async def handle_arena_challenge_friend(
    callback: CallbackQuery,
    *,
    arena_duel_id,
    session_local,
    user_onboarding_service,
    create_friend_challenge_from_arena_duel,
    build_friend_invite_link,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        try:
            challenge = await create_friend_challenge_from_arena_duel(
                session,
                creator_user_id=snapshot.user_id,
                arena_duel_id=arena_duel_id,
                now_utc=now_utc,
            )
        except (FriendChallengePaymentRequiredError, FriendChallengeLimitExceededError):
            await callback.message.answer(
                TEXTS_DE["msg.friend.challenge.limit.reached"],
                reply_markup=build_friend_challenge_limit_keyboard(),
            )
            await callback.answer()
            return
        except FriendChallengeAccessError:
            await callback.message.answer(
                TEXTS_DE["msg.friend.challenge.invalid"],
                reply_markup=build_arena_back_keyboard(),
            )
            await callback.answer()
            return

    await send_friend_challenge_invite(
        callback,
        challenge=challenge,
        build_friend_invite_link=build_friend_invite_link,
    )
    await callback.answer()
