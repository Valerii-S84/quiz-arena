from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import CallbackQuery

from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_back_keyboard,
    build_friend_challenge_finished_keyboard,
)
from app.bot.keyboards.home import build_home_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeCompletedError,
    FriendChallengeExpiredError,
    FriendChallengeFullError,
    FriendChallengeNotFoundError,
)


async def handle_friend_challenge_next(
    callback: CallbackQuery,
    *,
    friend_next_re,
    parse_uuid_callback,
    session_local,
    user_onboarding_service,
    game_session_service,
    resolve_opponent_label,
    build_friend_score_text,
    build_friend_ttl_text,
    send_friend_round_question,
) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    challenge_id = parse_uuid_callback(pattern=friend_next_re, callback_data=callback.data)
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
            round_start = await game_session_service.start_friend_challenge_round(
                session,
                user_id=snapshot.user_id,
                challenge_id=challenge_id,
                idempotency_key=f"start:friend:next:{challenge_id}:{callback.id}",
                now_utc=now_utc,
            )
        except FriendChallengeExpiredError:
            await callback.message.answer(
                TEXTS_DE["msg.friend.challenge.expired"],
                reply_markup=build_friend_challenge_finished_keyboard(challenge_id=str(challenge_id)),
            )
            await callback.answer()
            return
        except (
            FriendChallengeNotFoundError,
            FriendChallengeAccessError,
            FriendChallengeCompletedError,
            FriendChallengeFullError,
        ):
            await callback.message.answer(TEXTS_DE["msg.friend.challenge.invalid"], reply_markup=build_home_keyboard())
            await callback.answer()
            return

    summary_lines = [
        build_friend_score_text(
            challenge=round_start.snapshot,
            user_id=snapshot.user_id,
            opponent_label=await resolve_opponent_label(
                challenge=round_start.snapshot,
                user_id=snapshot.user_id,
            ),
        ),
    ]
    ttl_text = build_friend_ttl_text(challenge=round_start.snapshot, now_utc=now_utc)
    if ttl_text is not None:
        summary_lines.append(ttl_text)
    if round_start.already_answered_current_round:
        summary_lines.append(
            TEXTS_DE["msg.friend.challenge.all_answered.waiting"].format(
                total_rounds=round_start.snapshot.total_rounds,
                opponent_label=await resolve_opponent_label(
                    challenge=round_start.snapshot,
                    user_id=snapshot.user_id,
                ),
            )
        )
        await callback.message.answer(
            "\n".join(summary_lines),
            reply_markup=build_friend_challenge_back_keyboard(),
        )
        await callback.answer()
        return

    await send_friend_round_question(
        callback,
        snapshot_free_energy=snapshot.free_energy,
        snapshot_paid_energy=snapshot.paid_energy,
        round_start=round_start,
    )
    await callback.answer()
