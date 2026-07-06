from __future__ import annotations

from datetime import datetime

from aiogram.types import CallbackQuery

from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_limit_keyboard,
    build_friend_challenge_next_keyboard,
    build_friend_challenge_share_keyboard,
)
from app.bot.texts.de import TEXTS_DE
from app.game.arena_duels.analytics import ArenaPaywallContext


async def answer_friend_challenge_limit(
    callback: CallbackQuery,
    *,
    paywall_context: ArenaPaywallContext,
) -> None:
    message_answer = getattr(callback.message, "answer", None)
    if callable(message_answer):
        await message_answer(
            TEXTS_DE["msg.friend.challenge.limit.reached"],
            reply_markup=build_friend_challenge_limit_keyboard(paywall_context=paywall_context),
        )
    await callback.answer()


async def send_friend_challenge_created(
    callback: CallbackQuery,
    *,
    challenge,
    now_utc: datetime,
    build_friend_invite_link,
    build_friend_plan_text,
    build_friend_ttl_text,
) -> None:
    message_answer = getattr(callback.message, "answer", None)
    if not callable(message_answer):
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
    else:
        body_lines.insert(0, TEXTS_DE["msg.friend.challenge.created"])
    await message_answer(
        "\n".join(body_lines),
        reply_markup=build_friend_challenge_share_keyboard(
            invite_link=invite_link,
            challenge_id=str(challenge.challenge_id),
        ),
    )


async def notify_friend_rematch_opponent(
    callback: CallbackQuery,
    *,
    rematch,
    opponent_user_id: int | None,
    resolve_opponent_label,
    notify_opponent,
    build_friend_plan_text,
) -> None:
    if opponent_user_id is None:
        return
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
        reply_markup=build_friend_challenge_next_keyboard(challenge_id=str(rematch.challenge_id)),
    )
