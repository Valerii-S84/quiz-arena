from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import CallbackQuery

from app.bot.keyboards.friend_challenge import build_friend_challenge_next_keyboard
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeLimitExceededError,
    FriendChallengeNotFoundError,
    FriendChallengePaymentRequiredError,
)

from .friend_challenge_flow_helpers import (
    answer_friend_challenge_limit,
    notify_friend_rematch_opponent,
    send_friend_challenge_created,
)


async def handle_friend_challenge_create_selected(
    callback: CallbackQuery,
    *,
    session_local,
    user_onboarding_service,
    game_session_service,
    parse_challenge_rounds,
    build_friend_invite_link,
    build_friend_plan_text,
    build_friend_ttl_text,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    if callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    selected_rounds = parse_challenge_rounds(callback.data)
    if selected_rounds is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

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
                total_rounds=selected_rounds,
            )
        except (FriendChallengePaymentRequiredError, FriendChallengeLimitExceededError):
            await answer_friend_challenge_limit(
                callback,
                paywall_context="friend_create_limit",
            )
            return

    await send_friend_challenge_created(
        callback,
        challenge=challenge,
        now_utc=now_utc,
        build_friend_invite_link=build_friend_invite_link,
        build_friend_plan_text=build_friend_plan_text,
        build_friend_ttl_text=build_friend_ttl_text,
    )
    await callback.answer()


async def handle_friend_challenge_rematch(
    callback: CallbackQuery,
    *,
    friend_rematch_re,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    game_session_service,
    resolve_opponent_label,
    friend_opponent_user_id,
    notify_opponent,
    build_friend_plan_text,
    build_friend_ttl_text,
) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    challenge_id = parse_uuid_callback(pattern=friend_rematch_re, callback_data=callback.data)
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
            rematch = await game_session_service.create_friend_challenge_rematch(
                session,
                initiator_user_id=snapshot.user_id,
                challenge_id=challenge_id,
                now_utc=now_utc,
            )
        except FriendChallengePaymentRequiredError:
            await answer_friend_challenge_limit(
                callback,
                paywall_context="friend_rematch_limit",
            )
            return
        except (
            FriendChallengeNotFoundError,
            FriendChallengeAccessError,
        ):
            await callback.message.answer(
                TEXTS_DE["msg.friend.challenge.invalid"],
                reply_markup=build_home_keyboard(),
            )
            await callback.answer()
            return

    opponent_label = await resolve_opponent_label(
        challenge=rematch,
        user_id=snapshot.user_id,
    )
    rematch_lines = [
        TEXTS_DE["msg.friend.challenge.rematch.created"].format(opponent_label=opponent_label),
        build_friend_plan_text(total_rounds=rematch.total_rounds),
    ]
    rematch_ttl_text = build_friend_ttl_text(challenge=rematch, now_utc=now_utc)
    if rematch_ttl_text is not None:
        rematch_lines.append(rematch_ttl_text)
    await callback.message.answer(
        "\n".join(rematch_lines),
        reply_markup=build_friend_challenge_next_keyboard(challenge_id=str(rematch.challenge_id)),
    )

    opponent_user_id = friend_opponent_user_id(challenge=rematch, user_id=snapshot.user_id)
    await notify_friend_rematch_opponent(
        callback,
        rematch=rematch,
        opponent_user_id=opponent_user_id,
        resolve_opponent_label=resolve_opponent_label,
        notify_opponent=notify_opponent,
        build_friend_plan_text=build_friend_plan_text,
    )
    await callback.answer()
