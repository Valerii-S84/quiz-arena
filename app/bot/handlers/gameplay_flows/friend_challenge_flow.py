from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import CallbackQuery

from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_limit_keyboard,
    build_friend_challenge_next_keyboard,
    build_friend_challenge_share_keyboard,
)
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeLimitExceededError,
    FriendChallengeNotFoundError,
    FriendChallengePaymentRequiredError,
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
            await callback.message.answer(
                TEXTS_DE["msg.friend.challenge.limit.reached"],
                reply_markup=build_friend_challenge_limit_keyboard(),
            )
            await callback.answer()
            return

    invite_link = await build_friend_invite_link(callback, invite_token=challenge.invite_token)
    body_lines = [
        build_friend_plan_text(total_rounds=challenge.total_rounds),
        TEXTS_DE["msg.friend.challenge.created.short"],
    ]
    ttl_text = build_friend_ttl_text(challenge=challenge, now_utc=now_utc)
    if ttl_text is not None:
        body_lines.append(ttl_text)
    if invite_link is None:
        body_lines.insert(
            0,
            TEXTS_DE["msg.friend.challenge.created.fallback"].format(
                invite_token=challenge.invite_token
            ),
        )
        await callback.message.answer(
            "\n".join(body_lines),
            reply_markup=build_friend_challenge_share_keyboard(
                invite_link=None,
                challenge_id=str(challenge.challenge_id),
                total_rounds=challenge.total_rounds,
            ),
        )
    else:
        body_lines.insert(
            0,
            TEXTS_DE["msg.friend.challenge.created"],
        )
        await callback.message.answer(
            "\n".join(body_lines),
            reply_markup=build_friend_challenge_share_keyboard(
                invite_link=invite_link,
                challenge_id=str(challenge.challenge_id),
                total_rounds=challenge.total_rounds,
            ),
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
            await callback.message.answer(
                TEXTS_DE["msg.friend.challenge.limit.reached"],
                reply_markup=build_friend_challenge_limit_keyboard(),
            )
            await callback.answer()
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
    if opponent_user_id is not None:
        opponent_label_for_opponent = await resolve_opponent_label(
            challenge=rematch,
            user_id=opponent_user_id,
        )
        await notify_opponent(
            callback,
            opponent_user_id=opponent_user_id,
            text="\n".join(
                [
                    TEXTS_DE["msg.friend.challenge.rematch.invite"].format(
                        opponent_label=opponent_label_for_opponent
                    ),
                    build_friend_plan_text(total_rounds=rematch.total_rounds),
                ]
            ),
            reply_markup=build_friend_challenge_next_keyboard(
                challenge_id=str(rematch.challenge_id)
            ),
        )
    await callback.answer()
