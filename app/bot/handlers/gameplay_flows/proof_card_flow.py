from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import CallbackQuery

from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_back_keyboard,
    build_friend_challenge_result_share_keyboard,
)
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError


async def handle_friend_challenge_share_result(
    callback: CallbackQuery,
    *,
    friend_share_result_re,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    game_session_service,
    resolve_opponent_label,
    build_friend_proof_card_text,
    build_friend_result_share_url,
    emit_analytics_event,
    event_source_bot: str,
) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    challenge_id = parse_uuid_callback(pattern=friend_share_result_re, callback_data=callback.data)
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
            challenge = await game_session_service.get_friend_challenge_snapshot_for_user(
                session,
                user_id=snapshot.user_id,
                challenge_id=challenge_id,
                now_utc=now_utc,
            )
        except (
            FriendChallengeNotFoundError,
            FriendChallengeAccessError,
        ):
            await callback.message.answer(TEXTS_DE["msg.friend.challenge.invalid"], reply_markup=build_home_keyboard())
            await callback.answer()
            return

        if challenge.status not in {"COMPLETED", "EXPIRED"}:
            await callback.message.answer(
                TEXTS_DE["msg.friend.challenge.proof.not_ready"],
                reply_markup=build_friend_challenge_back_keyboard(),
            )
            await callback.answer()
            return

        opponent_label = await resolve_opponent_label(
            challenge=challenge,
            user_id=snapshot.user_id,
        )
        proof_card_text = build_friend_proof_card_text(
            challenge=challenge,
            user_id=snapshot.user_id,
            opponent_label=opponent_label,
        )
        share_url = await build_friend_result_share_url(
            callback,
            proof_card_text=proof_card_text,
        )
        if share_url is None:
            await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
            return

        await emit_analytics_event(
            session,
            event_type="friend_challenge_proof_card_share_clicked",
            source=event_source_bot,
            happened_at=now_utc,
            user_id=snapshot.user_id,
            payload={
                "challenge_id": str(challenge.challenge_id),
                "status": challenge.status,
                "total_rounds": challenge.total_rounds,
            },
        )

    await callback.message.answer(
        "\n".join([TEXTS_DE["msg.friend.challenge.proof.share.ready"], proof_card_text]),
        reply_markup=build_friend_challenge_result_share_keyboard(
            share_url=share_url,
            challenge_id=str(challenge.challenge_id),
        ),
    )
    await callback.answer()
